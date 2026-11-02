"""Turn plumbing: identity instructions, history, and the inbound hook that
makes Me. answer on WhatsApp (persisting the exchange)."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from langchain_core.messages import AIMessage, HumanMessage

from ..localstore.keystore import get_keystore
from ..providers.chat_model import chat_model_for_profile
from ..providers.profiles import load_key
from .turn import run_turn

log = logging.getLogger("medot.engine")

HISTORY_LIMIT = 20
NO_MODEL_REPLY = (
    "I can't think yet — open Medot Desktop → AI Providers and add a model "
    "profile (any provider, your key). Then message me again."
)

# Serialized per user: one Me. brain, no interleaved turns.
_turn_locks: dict[str, asyncio.Lock] = {}
_no_model_notified: set[str] = set()


def _lock_for(user_id: str) -> asyncio.Lock:
    if user_id not in _turn_locks:
        _turn_locks[user_id] = asyncio.Lock()
    return _turn_locks[user_id]


def chat_profile_row(client, user_id: str) -> dict | None:
    """The user's chat-purpose model profile (newest first)."""
    rows = (
        client.table("model_profiles")
        .select("id,name,provider,model,api_base")
        .eq("user_id", user_id)
        .eq("purpose", "chat")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def me_instructions(client, user_id: str) -> str:
    """Me.'s active instruction document (identity_instructions, newest)."""
    identity = (
        client.table("identities")
        .select("id")
        .eq("user_id", user_id)
        .eq("slug", "me")
        .limit(1)
        .execute()
        .data
        or []
    )
    if not identity:
        return "You are Me., the user's personal companion. Be warm, concise and honest."
    rows = (
        client.table("identity_instructions")
        .select("content_md")
        .eq("identity_id", identity[0]["id"])
        .eq("is_active", True)
        .order("version", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0]["content_md"] if rows else "You are Me., the user's personal companion."


def load_history(client, user_id: str, peer: str) -> list:
    """The last HISTORY_LIMIT messages of this conversation, in order."""
    conversation = (
        client.table("conversations")
        .select("id")
        .eq("user_id", user_id)
        .eq("channel", "whatsapp")
        .eq("peer", peer)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not conversation:
        return []
    rows = (
        client.table("messages")
        .select("direction,body")
        .eq("conversation_id", conversation[0]["id"])
        .order("occurred_at", desc=True)
        .limit(HISTORY_LIMIT)
        .execute()
        .data
        or []
    )
    return [
        AIMessage(content=r["body"]) if r["direction"] == "outbound" else HumanMessage(content=r["body"])
        for r in reversed(rows)
    ]


def persist_outbound(client, user_id: str, peer: str, transport: str, text: str) -> None:
    conversation = (
        client.table("conversations")
        .upsert(
            {"user_id": user_id, "channel": "whatsapp", "transport": transport, "peer": peer},
            on_conflict="user_id,channel,peer",
        )
        .execute()
        .data
        or []
    )
    client.table("messages").insert(
        {
            "user_id": user_id,
            "conversation_id": conversation[0]["id"],
            "direction": "outbound",
            "body": text,
            "occurred_at": datetime.now(UTC).isoformat(),
        }
    ).execute()


def resolve_chat_model(client, user_id: str):
    """(model instance, None) or (None, reason) when no usable chat profile."""
    profile = chat_profile_row(client, user_id)
    if not profile:
        return None, NO_MODEL_REPLY
    key = load_key(get_keystore(), user_id, profile["id"])
    if not key:
        return None, NO_MODEL_REPLY
    model = chat_model_for_profile(profile["provider"], profile["model"], profile["api_base"], key)
    return model, None


async def _send_no_model(client, user_id: str, envelope) -> None:
    from ..whatsapp import manager as wa_manager

    try:
        await wa_manager.get_manager().send(NO_MODEL_REPLY, transport_name=envelope.transport, to=envelope.peer)
    except Exception:  # noqa: BLE001 - transport may be down; the console shows status
        log.warning("could not deliver the no-model notice")


async def handle_inbound(client, user_id: str, envelope) -> None:
    """The manager's on_message hook: Me. thinks and replies on the same route."""
    if envelope.transport not in ("agent_platform", "baileys"):
        return
    async with _lock_for(user_id):
        try:
            model, _notice = await asyncio.to_thread(resolve_chat_model, client, user_id)
            if model is None:
                if envelope.peer not in _no_model_notified:
                    _no_model_notified.add(envelope.peer)
                    await _send_no_model(client, user_id, envelope)
                return
            instructions = await asyncio.to_thread(me_instructions, client, user_id)
            history = await asyncio.to_thread(load_history, client, user_id, envelope.peer)
            reply = await run_turn(
                model,
                instructions,
                [*history, HumanMessage(content=envelope.text)],
                thread_id=f"u:{user_id}:c:{envelope.peer}:r:turn",
            )
            await asyncio.to_thread(persist_outbound, client, user_id, envelope.peer, envelope.transport, reply)
            from ..whatsapp import manager as wa_manager

            await wa_manager.get_manager().send(reply, transport_name=envelope.transport, to=envelope.peer)
        except Exception:
            log.exception("turn failed for %s", user_id)
