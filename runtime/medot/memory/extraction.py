"""Memory extraction (M3a): after each exchange, remember.

Two layers, per docs/medot/04 + 11 §6:
  1. Episodes — the raw exchange goes into `memory_episodes` (no LLM needed).
  2. Facts — the user's extraction-purpose model profile reads the exchange
     and returns structured facts; each becomes knowledge_nodes (+ an edge
     when a subject/object pair forms one). Extraction binds ONLY to the
     extraction profile — no cross-profile fallback for private content.

Best effort by design: a failed extraction never breaks the conversation.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import litellm
from pydantic import BaseModel

from ..localstore.keystore import get_keystore
from ..providers.profiles import load_key

log = logging.getLogger("medot.memory")

EXTRACTION_PROMPT = """You maintain the knowledge graph of a user's life.
From the exchange below, extract durable facts worth remembering (habits,
plans, measurements, relationships, preferences, events). Ignore small talk.
Reply with ONLY a JSON object:
{"facts": [{"subject": "<entity or the user>", "relation": "<verb phrase>",
            "object": "<value/entity>", "domain": "<one word, e.g. health>"}]}
Return {"facts": []} when nothing durable was said. Max 5 facts."""

EXTRACTION_MAX_TOKENS = 400


class Fact(BaseModel):
    subject: str
    relation: str
    object: str
    domain: str = "general"


class Extraction(BaseModel):
    facts: list[Fact]


def extraction_profile_row(client, user_id: str) -> dict | None:
    rows = (
        client.table("model_profiles")
        .select("id,provider,model,api_base")
        .eq("user_id", user_id)
        .eq("purpose", "extraction")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def save_episode(client, user_id: str, peer: str, user_text: str, me_text: str) -> None:
    """The exchange itself, always remembered."""
    client.table("memory_episodes").insert(
        {
            "user_id": user_id,
            "kind": "message",
            "content": f"{peer} said: {user_text}\nMe. replied: {me_text}",
            "occurred_at": datetime.now(UTC).isoformat(),
            "extraction_status": "pending",
        }
    ).execute()


def save_facts(client, user_id: str, facts: list[Fact]) -> int:
    """Upsert subject/object nodes, then the edge between them."""

    domain = _global_domain_id(client, user_id)
    saved = 0
    for fact in facts:
        subject_id = _upsert_node(client, user_id, domain, "entity", fact.subject)
        object_id = _upsert_node(client, user_id, domain, "fact", fact.object, f"{fact.relation} {fact.object}")
        if subject_id and object_id:
            client.table("knowledge_edges").insert(
                {
                    "user_id": user_id,
                    "domain_id": domain,
                    "src_node_id": subject_id,
                    "dst_node_id": object_id,
                    "relation": fact.relation[:120],
                    "fact": f"{fact.subject} {fact.relation} {fact.object}",
                }
            ).execute()
            saved += 1
    return saved


def _global_domain_id(client, user_id: str) -> str | None:
    rows = (
        client.table("knowledge_domains")
        .select("id")
        .eq("user_id", user_id)
        .eq("slug", "global")
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0]["id"] if rows else None


def _upsert_node(client, user_id: str, domain_id: str | None, node_type: str, name: str, summary: str = "") -> str | None:
    rows = (
        client.table("knowledge_nodes")
        .select("id")
        .eq("user_id", user_id)
        .eq("node_type", node_type)
        .eq("name", name)
        .limit(1)
        .execute()
        .data
        or []
    )
    if rows:
        return rows[0]["id"]
    inserted = (
        client.table("knowledge_nodes")
        .insert(
            {
                "user_id": user_id,
                "domain_id": domain_id,
                "node_type": node_type,
                "name": name[:200],
                "summary": summary[:500],
            }
        )
        .execute()
        .data
        or []
    )
    return inserted[0]["id"] if inserted else None


async def extract_facts(client, user_id: str, exchange_text: str) -> int:
    """LLM extraction via the extraction profile. Returns the fact count."""
    profile = extraction_profile_row(client, user_id)
    if not profile:
        return 0
    key = load_key(get_keystore(), user_id, profile["id"])
    if not key:
        return 0
    from ..providers.discovery import litellm_target

    model_string, api_base = litellm_target(profile["provider"], profile["model"], profile["api_base"])
    response = await litellm.acompletion(
        model=model_string,
        api_key=key,
        api_base=api_base,
        messages=[
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": exchange_text[:4000]},
        ],
        max_tokens=EXTRACTION_MAX_TOKENS,
        num_retries=0,
    )
    raw = (response.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        extraction = Extraction.model_validate(data)
    except Exception:  # noqa: BLE001 - a malformed extraction is simply dropped
        log.warning("unparseable extraction response (%d chars)", len(raw))
        return 0
    return await asyncio_safe_save(client, user_id, extraction.facts)


async def asyncio_safe_save(client, user_id: str, facts: list[Fact]) -> int:
    import asyncio

    return await asyncio.to_thread(save_facts, client, user_id, facts)
