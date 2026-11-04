"""Medot's tool registry — the authority (doc 11 §4).

Tool definitions live here; grants live in Supabase (`identity_tool_grants`).
LangChain is only the interface: `build_authorized_tools` converts granted
ToolDefs into LangChain tools whose invocation re-checks the grant
server-side on every call. The model can choose tools, never grant them.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ToolDef:
    key: str  # the registry key stored in identity_tool_grants
    name: str  # the function name the model sees
    description: str
    args_model: type[BaseModel]
    requires_approval: bool
    handler: Callable[..., Awaitable[dict | str]]  # async (client, user_id, **args) -> result

    def proposal(self, args: dict[str, Any]) -> str:
        """One-line proposal shown to the user when approval is required."""
        return f"{self.name}: {args}"


# ---------------------------------------------------------------------------
# Built-in knowledge tools (real, M3a-backed)
# ---------------------------------------------------------------------------
class RecallArgs(BaseModel):
    query: str = Field(description="What to look for in the user's knowledge")


class RememberArgs(BaseModel):
    subject: str = Field(description="Who or what the fact is about")
    relation: str = Field(description="Verb phrase, e.g. 'walked' or 'plans to run'")
    object: str = Field(description="The value or entity of the fact")
    domain: str = Field(default="general", description="One word, e.g. health")


class ForgetArgs(BaseModel):
    match: str = Field(description="Text to match against remembered facts — everything matching is forgotten")


async def _recall(client, user_id: str, query: str) -> dict:
    like = f"%{query}%"
    nodes = (
        client.table("knowledge_nodes")
        .select("name,summary")
        .eq("user_id", user_id)
        .or_(f"name.ilike.{like},summary.ilike.{like}")
        .limit(10)
        .execute()
        .data
        or []
    )
    edges = (
        client.table("knowledge_edges")
        .select("fact")
        .eq("user_id", user_id)
        .ilike("fact", like)
        .limit(10)
        .execute()
        .data
        or []
    )
    return {
        "nodes": [f"{n['name']}" + (f" — {n['summary']}" if n.get("summary") else "") for n in nodes],
        "facts": [e["fact"] for e in edges],
    }


async def _remember(client, user_id: str, subject: str, relation: str, object: str, domain: str = "general") -> dict:
    from ..memory.extraction import Fact, save_facts

    saved = save_facts(client, user_id, [Fact(subject=subject, relation=relation, object=object, domain=domain)])
    return {"saved": saved, "fact": f"{subject} {relation} {object}"}


async def _forget(client, user_id: str, match: str) -> dict:
    like = f"%{match}%"
    edges = (
        client.table("knowledge_edges")
        .select("id,fact")
        .eq("user_id", user_id)
        .ilike("fact", like)
        .limit(50)
        .execute()
        .data
        or []
    )
    for edge in edges:
        client.table("knowledge_edges").delete().eq("id", edge["id"]).execute()
    return {"forgotten": len(edges), "facts": [e["fact"] for e in edges]}


DEFAULT_TOOLS: list[ToolDef] = [
    ToolDef(
        key="knowledge.recall",
        name="recall_knowledge",
        description="Search what you remember about the user (facts and topics).",
        args_model=RecallArgs,
        requires_approval=False,
        handler=_recall,
    ),
    ToolDef(
        key="knowledge.remember",
        name="remember_fact",
        description="Save a durable fact about the user's life into their knowledge graph.",
        args_model=RememberArgs,
        requires_approval=False,
        handler=_remember,
    ),
    ToolDef(
        key="knowledge.forget",
        name="forget_fact",
        description="FORGET facts matching text — destructive, deletes them from the graph.",
        args_model=ForgetArgs,
        requires_approval=True,
        handler=_forget,
    ),
]


def tool_by_name(name: str) -> ToolDef | None:
    return next((t for t in DEFAULT_TOOLS if t.name == name), None)


def ensure_me_grants(client, user_id: str, identity_id: str) -> dict[str, dict]:
    """Grant the default tools to Me. on first use; return the grant map.

    key -> {requires_approval}. The grants table stays authoritative after
    seeding — callers re-read it on every tool build.
    """
    rows = (
        client.table("identity_tool_grants")
        .select("tool_key,requires_approval")
        .eq("identity_id", identity_id)
        .execute()
        .data
        or []
    )
    if not rows:
        for tool in DEFAULT_TOOLS:
            client.table("identity_tool_grants").insert(
                {
                    "user_id": user_id,
                    "identity_id": identity_id,
                    "tool_key": tool.key,
                    "requires_approval": tool.requires_approval,
                }
            ).execute()
        rows = (
            client.table("identity_tool_grants")
            .select("tool_key,requires_approval")
            .eq("identity_id", identity_id)
            .execute()
            .data
            or []
        )
    return {r["tool_key"]: r for r in rows}


def granted_tools(client, user_id: str, identity_id: str) -> list[ToolDef]:
    """ToolDefs the identity is actually granted (server-side filter)."""
    grants = ensure_me_grants(client, user_id, identity_id)
    return [t for t in DEFAULT_TOOLS if t.key in grants]
