"""Turn plumbing: identity instructions, history, and the inbound hook that
makes Me. answer (persisting the exchange) — now with the M4b approval flow.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from ..localstore import paths
from ..localstore.keystore import get_keystore
from ..providers.chat_model import chat_model_for_profile
from ..providers.profiles import load_key
from ..tools.registry import granted_tools
from .turn import resume_turn, run_turn

log = logging.getLogger("medot.engine")

HISTORY_LIMIT = 20
NO_MODEL_REPLY = (
    "I can't think yet — open Medot Desktop → AI Providers and add a model "
    "profile (any provider, your key). Then message me again."
)
YES = {"yes", "y", "confirm", "do it", "yeah", "ok"}
NO = {"no", "n", "stop", "cancel"}

# Serialized per user: one Me. brain, no interleaved turns.
_turn_locks: dict[str, asyncio.Lock] = {}
_no_model_notified: set[str] = set()
_savers: dict[str, Any] = {}


def _lock_for(user_id: str) -> asyncio.Lock:
    if user_id not in _turn_locks:
        _turn_locks[user_id] = asyncio.Lock()
    return _turn_locks[user_id]


async def _saver_for(user_id: str) -> Any:
    """One SQLite checkpoint file per user (doc 11 §9); in-memory fallback."""
    if user_id in _savers:
        return _savers[user_id]
    try:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        root = paths.ensure_layout()["checkpoints"]
        conn = await aiosqlite.connect(str(root / f"{user_id}.sqlite"))
        saver = AsyncSqliteSaver(conn)
        _savers[user_id] = saver
        return saver
    except Exception:  # noqa: BLE001 - execution state only; never canonical
        from langgraph.checkpoint.memory import MemorySaver

        saver = MemorySaver()
        _savers[user_id] = saver
        return saver


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


def me_identity_id(client, user_id: str) -> str | None:
    rows = (
        client.table("identities")
        .select("id")
        .eq("user_id", user_id)
        .eq("slug", "me")
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0]["id"] if rows else None


def me_instructions(client, user_id: str) -> str:
    """Me.'s active instruction document (identity_instructions, newest)."""
    identity_id = me_identity_id(client, user_id)
    if not identity_id:
        return "You are Me., the user's personal companion. Be warm, concise and honest."
    rows = (
        client.table("identity_instructions")
        .select("content_md")
        .eq("identity_id", identity_id)
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


# ---------------------------------------------------------------------------
# runs, approvals, activity (M4b)
# ---------------------------------------------------------------------------
def _new_agent_run(client, user_id: str, identity_id: str | None, trigger: str = "inbound") -> str | None:
    rows = (
        client.table("agent_runs")
        .insert({"user_id": user_id, "identity_id": identity_id, "trigger": trigger})
        .execute()
        .data
        or []
    )
    return rows[0]["id"] if rows else None


def _finish_agent_run(client, run_row_id: str | None, status: str, error: str | None = None) -> None:
    if not run_row_id:
        return
    patch: dict = {"status": status, "ended_at": datetime.now(UTC).isoformat()}
    if error:
        patch["error"] = error[:500]
    client.table("agent_runs").update(patch).eq("id", run_row_id).execute()


def _pending_approval(client, user_id: str, peer: str) -> dict | None:
    rows = (
        client.table("approvals")
        .select("id,action,summary,payload,created_at,expires_at")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .eq("payload->>peer", peer)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    row = rows[0]
    expires = row.get("expires_at")
    if expires and datetime.fromisoformat(str(expires)) < datetime.now(UTC):
        client.table("approvals").update({"status": "expired"}).eq("id", row["id"]).execute()
        return None
    return row


def parse_decision(text: str) -> bool | None:
    cleaned = (text or "").strip().lower().rstrip(".!")
    if cleaned in YES:
        return True
    if cleaned in NO:
        return False
    return None


def _decide(client, user_id: str, approval_id: str, approved: bool) -> None:
    client.table("approvals").update(
        {"status": "approved" if approved else "denied", "decided_at": datetime.now(UTC).isoformat()}
    ).eq("id", approval_id).execute()


def _log_activity(client, user_id: str, identity_id: str | None, event: str, detail: dict) -> None:
    client.table("activity_events").insert(
        {"user_id": user_id, "identity_id": identity_id, "event": event, "detail": detail}
    ).execute()


def _tools_for_me(client, user_id: str) -> list:
    identity_id = me_identity_id(client, user_id)
    if not identity_id:
        return []
    return granted_tools(client, user_id, identity_id)


async def _send_no_model(client, user_id: str, peer: str, transport: str) -> None:
    from ..whatsapp import manager as wa_manager

    try:
        await wa_manager.get_manager().send(NO_MODEL_REPLY, transport_name=transport, to=peer)
    except Exception:  # noqa: BLE001 - transport may be down; the console shows status
        log.warning("could not deliver the no-model notice")


def remember_exchange_sync(client, user_id: str, peer: str, user_text: str, reply: str) -> None:
    """Sync memory save for endpoint paths (episode always)."""
    from ..memory import extraction as mem

    mem.save_episode(client, user_id, peer, user_text, reply)


async def remember_exchange(client, user_id: str, user_text: str, reply: str) -> None:
    """Episodes always; LLM fact extraction when an extraction profile exists."""
    from ..memory import extraction as mem

    try:
        await asyncio.to_thread(mem.save_episode, client, user_id, "whatsapp", user_text, reply)
        exchange = f"User said: {user_text}\nMe. replied: {reply}"
        count = await mem.extract_facts(client, user_id, exchange)
        log.info("remembered exchange (%d facts)", count)
    except Exception:
        log.exception("memory extraction failed")


async def _deliver(manager, transport: str, peer: str, text: str) -> None:
    """Deliver via the transport; the desktop seam reads the reply from DB."""
    if transport == "desktop":
        return
    await manager.send(text, transport_name=transport, to=peer)


async def _run_inbound_flow(client, user_id: str, peer: str, transport: str, text: str) -> None:
    """The whole Me. flow: approvals first, then a fresh agent turn."""
    model, notice = await asyncio.to_thread(resolve_chat_model, client, user_id)
    if model is None:
        if peer not in _no_model_notified:
            _no_model_notified.add(peer)
            await _send_no_model(client, user_id, peer, transport)
        return
    tools = await asyncio.to_thread(_tools_for_me, client, user_id)
    instructions = await asyncio.to_thread(me_instructions, client, user_id)
    identity_id = await asyncio.to_thread(me_identity_id, client, user_id)
    saver = await _saver_for(user_id)
    from ..whatsapp import manager as wa_manager

    # 1. a pending approval turns this message into a decision
    pending = await asyncio.to_thread(_pending_approval, client, user_id, peer)
    if pending:
        decision = parse_decision(text)
        if decision is None:
            await wa_manager.get_manager().send(
                "Please reply YES to allow it, or NO to keep everything.",
                transport_name=transport,
                to=peer,
            )
            return
        thread_id = (pending.get("payload") or {}).get("thread_id", "")
        reply = await resume_turn(
            model, instructions,
            thread_id=thread_id, checkpointer=saver, tools=tools,
            client=client, user_id=user_id, decision={"approved": decision},
        )
        await asyncio.to_thread(_decide, client, user_id, pending["id"], decision)
        await asyncio.to_thread(_finish_agent_run, client, pending.get("run_id"), "succeeded")
        await asyncio.to_thread(
            _log_activity, client, user_id, identity_id, "approval.decided",
            {"approval": pending["id"], "approved": decision, "action": pending.get("action")},
        )
        await asyncio.to_thread(persist_outbound, client, user_id, peer, transport, reply)
        await _deliver(wa_manager.get_manager(), transport, peer, reply)
        asyncio.create_task(remember_exchange(client, user_id, text, reply))
        return

    # 2. a fresh agent turn
    run_row = await asyncio.to_thread(_new_agent_run, client, user_id, identity_id)
    run_thread = f"u:{user_id}:c:{peer}:r:{uuid4().hex}"
    result = await run_turn(
        model, instructions,
        [*await asyncio.to_thread(load_history, client, user_id, peer), HumanMessage(content=text)],
        thread_id=run_thread, checkpointer=saver, tools=tools, client=client, user_id=user_id,
    )

    if result["interrupt"]:
        payload = {
            "thread_id": run_thread,
            "peer": peer,
            "tool": result["interrupt"].get("tool"),
            "args": result["interrupt"].get("args"),
        }
        await asyncio.to_thread(
            client.table("approvals").insert,
            {
                "user_id": user_id,
                "run_id": run_row,
                "identity_id": identity_id,
                "action": result["interrupt"].get("tool"),
                "summary": str(result["interrupt"].get("proposal", ""))[:500],
                "payload": payload,
                "status": "pending",
                "channel": transport,
            },
        )
        await asyncio.to_thread(_finish_agent_run, client, run_row, "awaiting_approval")
        proposal = f"{result['interrupt'].get('proposal', 'May I?')}\nReply YES to allow, NO to keep everything."
        await asyncio.to_thread(persist_outbound, client, user_id, peer, transport, proposal)
        await wa_manager.get_manager().send(proposal, transport_name=transport, to=peer)
        return

    reply = result["reply"] or "I'm here — say more?"
    await asyncio.to_thread(_finish_agent_run, client, run_row, "succeeded")
    await asyncio.to_thread(persist_outbound, client, user_id, peer, transport, reply)
    await _deliver(wa_manager.get_manager(), transport, peer, reply)
    asyncio.create_task(remember_exchange(client, user_id, text, reply))


async def handle_inbound(client, user_id: str, envelope) -> None:
    """The manager's on_message hook: Me. thinks, acts, asks, replies."""
    if envelope.transport not in ("agent_platform", "baileys"):
        return
    async with _lock_for(user_id):
        try:
            await _run_inbound_flow(client, user_id, envelope.peer, envelope.transport, envelope.text)
        except Exception:
            log.exception("turn failed for %s", user_id)
            await asyncio.to_thread(_fail_open_run, client, user_id)


def _fail_open_run(client, user_id: str) -> None:
    rows = (
        client.table("agent_runs")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "running")
        .order("started_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if rows:
        _finish_agent_run(client, rows[0]["id"], "failed", "turn failed")
