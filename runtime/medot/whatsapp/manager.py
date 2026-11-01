"""WhatsApp transport manager — Route 1 (official Agent Platform) and
Route 2 (Baileys bridge) behind one contract, connectable individually or
together (docs/medot/03, product-owner decision 2026-11-02).

Each transport long-polls for inbound updates (no inbound ports, no relay),
normalizes messages into `Envelope`s, dedupes them, and the manager persists
them to Supabase (`conversations` + `messages`, RLS-scoped to the signed-in
user). Outbound sends are split at WhatsApp's 4096-char limit; the Agent
Platform client paces itself under Meta's per-minute budgets.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .. import __version__
from ..localstore import keystore as keystore_mod
from ..localstore import paths
from . import connection as wa_conn
from .agent_platform import (
    AgentPlatformClient,
    AuthError,
    NotCreatorError,
    PollConflict,
    Retryable,
    split_text,
)
from .baileys import BaileysBridge, BridgeSettings

log = logging.getLogger("medot.whatsapp")

PROVIDER_AGENT_PLATFORM = wa_conn.PROVIDER  # whatsapp_agent_platform
PROVIDER_BAILEYS = "whatsapp_baileys"
AGENT_PLATFORM_NAME = "agent_platform"
BAILEYS_NAME = "baileys"

POLL_TIMEOUT = 20
MAX_BACKOFF = 60.0
POLL_CONFLICT_LIMIT = 3
SEEN_CAP = 4096


@dataclass
class Envelope:
    """One normalized inbound message, transport-agnostic."""

    transport: str
    message_id: str
    peer: str
    chat: str
    sender: str
    text: str
    sender_name: str | None = None
    media: dict | None = None
    timestamp: int = 0
    raw: dict = field(default_factory=dict, repr=False)


class Transport:
    """Base: long-poll loop, error state, backoff. Subclasses implement poll_once/send."""

    name: str = ""
    provider: str = ""

    def __init__(self) -> None:
        self.error: str | None = None
        self.started_at: float | None = None
        self.last_inbound_at: float | None = None
        self.last_peer: str | None = None
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    # -- lifecycle ----------------------------------------------------------
    async def start(self) -> None:
        self.error = None
        self._stopping.clear()
        self.started_at = time.time()
        self._task = asyncio.create_task(self._loop(), name=f"wa-{self.name}")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:  # the loop task being torn down
                pass
            except Exception:  # noqa: BLE001, S110 - loop teardown is best effort
                pass
            self._task = None

    # -- loop ---------------------------------------------------------------
    async def _loop(self) -> None:
        backoff = 1.0
        conflicts = 0
        while not self._stopping.is_set():
            try:
                items = await self.poll_once()
                backoff = 1.0
                conflicts = 0
                for envelope in items:
                    self.last_inbound_at = time.time()
                    self.last_peer = envelope.peer
                    await self.on_inbound(envelope)
            except PollConflict:
                # Another poller replaced ours (a second runtime on the same key).
                conflicts += 1
                if conflicts >= POLL_CONFLICT_LIMIT:
                    self.error = "another device is polling this agent's updates"
                    log.warning("%s: giving up after repeated poll conflicts", self.name)
                    return
                await asyncio.sleep(5)
            except AuthError as exc:
                self.error = str(exc)
                log.error("%s: %s", self.name, exc.describe())
                return
            except NotCreatorError as exc:
                self.error = "Meta refused the send: only the agent's creator can receive replies"
                log.error("%s: %s", self.name, exc.describe())
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
            except (TimeoutError, Retryable) as exc:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
                if isinstance(exc, Retryable) and backoff >= MAX_BACKOFF:
                    log.debug("%s: %s", self.name, exc)
            except Exception as exc:
                self.error = str(exc)
                log.exception("%s: poll loop error", self.name)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

    async def poll_once(self) -> list[Envelope]:  # pragma: no cover - interface
        raise NotImplementedError

    async def send(self, peer: str, text: str, reply_to: str | None = None) -> str:  # pragma: no cover
        raise NotImplementedError

    async def on_inbound(self, envelope: Envelope) -> None:  # pragma: no cover - set by manager
        raise NotImplementedError

    def status(self) -> dict:
        return {
            "transport": self.name,
            "provider": self.provider,
            "running": self._task is not None and not self._task.done(),
            "error": self.error,
            "connected_at": self.started_at and time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started_at)),
            "last_inbound_at": self.last_inbound_at
            and time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.last_inbound_at)),
        }


# ---------------------------------------------------------------------------
# Route 1 — official WhatsApp Agent Platform
# ---------------------------------------------------------------------------
class AgentPlatformTransport(Transport):
    name = AGENT_PLATFORM_NAME
    provider = PROVIDER_AGENT_PLATFORM

    def __init__(self, api_key: str, *, on_inbound, base_url: str | None = None) -> None:
        super().__init__()
        self._client = AgentPlatformClient(api_key, **({"base_url": base_url} if base_url else {}))
        self._offset: int | None = None
        self._on_inbound = on_inbound

    async def poll_once(self) -> list[Envelope]:
        updates = await self._client.get_updates(self._offset, timeout=POLL_TIMEOUT)
        if updates.next_offset is not None:
            self._offset = updates.next_offset

        envelopes: list[Envelope] = []
        profiles = {c.get("wa_id"): c.get("profile", {}).get("name") for c in updates.contacts if c.get("wa_id")}
        for message in updates.messages:
            kind = message.get("type")
            body_obj = message.get(kind) if isinstance(message.get(kind), dict) else {}
            text = ""
            media: dict | None = None
            if kind == "text":
                text = str(body_obj.get("body") or "")
            elif kind in ("image", "video", "audio", "document", "sticker"):
                media = {
                    "kind": kind,
                    "media_id": body_obj.get("id"),
                    "mime": body_obj.get("mime_type"),
                    "sha256": body_obj.get("sha256"),
                    "filename": body_obj.get("filename"),
                    "caption": body_obj.get("caption"),
                }
            elif kind == "location":
                media = {"kind": "location", **{k: v for k, v in body_obj.items()}}
            if not text and not media:
                continue
            peer = str(message.get("from") or "")
            envelopes.append(
                Envelope(
                    transport=self.name,
                    message_id=str(message.get("id") or ""),
                    peer=peer,
                    chat=peer,
                    sender=peer,
                    sender_name=profiles.get(peer),
                    text=text,
                    media=media,
                    timestamp=int(message.get("timestamp") or 0),
                    raw=message,
                )
            )
            # Read receipt (budgeted, best effort) — typing indicator while we work.
            try:
                await self._client.mark_read(str(message.get("id")), typing=True)
            except Exception:  # noqa: BLE001, S110 - receipt failure never blocks delivery
                pass
        return envelopes

    async def send(self, peer: str, text: str, reply_to: str | None = None) -> str:
        last = ""
        for chunk in split_text(text):
            last = await self._client.send_text(peer, chunk, reply_to=reply_to)
        return last

    async def on_inbound(self, envelope: Envelope) -> None:
        await self._on_inbound(envelope)

    async def stop(self) -> None:
        await super().stop()
        await self._client.aclose()

    def status(self) -> dict:
        return {**super().status(), "peer_hint": self.last_peer}


# ---------------------------------------------------------------------------
# Route 2 — Baileys bridge (unofficial)
# ---------------------------------------------------------------------------
class BaileysTransport(Transport):
    name = BAILEYS_NAME
    provider = PROVIDER_BAILEYS

    def __init__(self, bridge: BaileysBridge, *, on_inbound) -> None:
        super().__init__()
        self._bridge = bridge
        self._cursor = 0
        self._on_inbound = on_inbound

    async def start(self) -> None:
        await self._bridge.start()
        await super().start()

    async def poll_once(self) -> list[Envelope]:
        updates, cursor = await self._bridge.updates(self._cursor, timeout=POLL_TIMEOUT)
        self._cursor = max(self._cursor, cursor)
        envelopes = []
        for u in updates:
            envelopes.append(
                Envelope(
                    transport=self.name,
                    message_id=str(u.get("id") or ""),
                    peer=str(u.get("peer") or u.get("chat") or ""),
                    chat=str(u.get("chat") or ""),
                    sender=str(u.get("sender") or ""),
                    text=str(u.get("text") or ""),
                    sender_name=u.get("sender_name"),
                    media=u.get("media"),
                    timestamp=int(u.get("timestamp") or 0),
                    raw=u,
                )
            )
        return envelopes

    async def send(self, peer: str, text: str, reply_to: str | None = None) -> str:
        return await self._bridge.send(peer, text)

    async def on_inbound(self, envelope: Envelope) -> None:
        await self._on_inbound(envelope)

    async def stop(self) -> None:
        await super().stop()
        await self._bridge.stop()

    async def qr(self) -> dict:
        return await self._bridge.qr()

    @property
    def bridge(self) -> BaileysBridge:
        return self._bridge


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    """Owns the active transports for the signed-in user; persists connections."""

    def __init__(self) -> None:
        self._transports: dict[str, Transport] = {}
        self._lock = asyncio.Lock()
        self._seen: dict[str, None] = {}  # insertion-ordered dedupe set
        self.inbound_count = 0
        self.on_message = None  # optional async hook (engine, later milestones)
        self._client = None  # Supabase client of the connected user (RLS-scoped)
        self._user_id: str | None = None

    # -- inbound ------------------------------------------------------------
    async def _handle(self, envelope: Envelope) -> None:
        key = f"{envelope.transport}:{envelope.message_id}"
        if key in self._seen:
            return
        self._seen[key] = None
        if len(self._seen) > SEEN_CAP:
            for old in list(self._seen)[: len(self._seen) - SEEN_CAP]:
                self._seen.pop(old, None)
        self.inbound_count += 1
        log.info("wa inbound (%s) from %s: %s", envelope.transport, envelope.sender, envelope.text[:60])
        if self.on_message:
            try:
                await self.on_message(envelope)
            except Exception:
                log.exception("on_message hook failed")
        if self._client and self._user_id:
            try:
                await asyncio.to_thread(persist_message, self._client, self._user_id, envelope)
            except Exception:
                log.exception("inbound persistence failed")

    # -- agent platform -----------------------------------------------------
    async def connect_agent_platform(self, client, user_id: str, api_key: str) -> dict:
        """Validate + store the key (keystore), record the link, start polling."""
        await self.disconnect_agent_platform(client, user_id, record=False)
        status = await asyncio.to_thread(wa_conn.connect, client, user_id, api_key)
        if not status.connected:
            raise RuntimeError("connection was recorded as not connected")
        self._client = client
        self._user_id = user_id
        transport = AgentPlatformTransport(api_key, on_inbound=self._handle)
        await transport.start()
        self._transports[AGENT_PLATFORM_NAME] = transport
        return self.status()["agent_platform"]

    async def disconnect_agent_platform(self, client, user_id: str, *, record: bool = True) -> None:
        transport = self._transports.pop(AGENT_PLATFORM_NAME, None)
        if transport:
            await transport.stop()
        if record:
            await asyncio.to_thread(wa_conn.disconnect, client, user_id)

    # -- baileys ------------------------------------------------------------
    async def connect_baileys(self, client, user_id: str, settings: BridgeSettings) -> dict:
        """Record the link + policy, spawn the bridge, start polling.

        Pairing is asynchronous: poll `GET /whatsapp/baileys/qr` until `paired`.
        """
        await self.disconnect_baileys(client, user_id, record=False)
        settings.validate()
        await asyncio.to_thread(self._record_baileys, client, user_id, settings)
        bridge = BaileysBridge(settings)
        transport = BaileysTransport(bridge, on_inbound=self._handle)
        await transport.start()
        self._transports[BAILEYS_NAME] = transport
        self._client = client
        self._user_id = user_id
        return self.status()["baileys"]

    async def disconnect_baileys(self, client, user_id: str, *, record: bool = True) -> None:
        transport = self._transports.pop(BAILEYS_NAME, None)
        if transport:
            await transport.stop()
        if record:
            await asyncio.to_thread(self._revoke_baileys, client, user_id)

    async def baileys_logout(self, client, user_id: str) -> None:
        """Unpair the WhatsApp session entirely (QR needed again next time)."""
        transport = self._transports.get(BAILEYS_NAME)
        if isinstance(transport, BaileysTransport):
            self._transports.pop(BAILEYS_NAME, None)
            await transport.bridge.logout()
        else:
            import shutil

            root = paths.ensure_layout()["state"]
            shutil.rmtree(root / "whatsapp" / "baileys-session", ignore_errors=True)
        await asyncio.to_thread(self._revoke_baileys, client, user_id)

    async def baileys_qr(self) -> dict:
        transport = self._transports.get(BAILEYS_NAME)
        if not isinstance(transport, BaileysTransport):
            raise RuntimeError("the Baileys route is not connected")  # noqa: TRY004
        return await transport.qr()

    # -- persistence helpers (sync; run via to_thread) ------------------------
    def _record_baileys(self, client, user_id: str, settings: BridgeSettings) -> None:
        rows = (
            client.table("connector_accounts")
            .select("id")
            .eq("user_id", user_id)
            .eq("provider", PROVIDER_BAILEYS)
            .limit(1)
            .execute()
            .data
            or []
        )
        row = {
            "user_id": user_id,
            "provider": PROVIDER_BAILEYS,
            "account_label": f"Baileys ({settings.mode} mode)",
            "status": "connected",
        }
        if rows:
            client.table("connector_accounts").update(row).eq("id", rows[0]["id"]).execute()
        else:
            client.table("connector_accounts").insert(row).execute()
        set_user_setting(client, user_id, "whatsapp_baileys", settings.to_dict())

    def _revoke_baileys(self, client, user_id: str) -> None:
        client.table("connector_accounts").update({"status": "revoked"}).eq(
            "user_id", user_id
        ).eq("provider", PROVIDER_BAILEYS).execute()

    # -- startup resume ------------------------------------------------------
    async def resume(self, client, user_id: str) -> None:
        """Reconnect whatever was connected before the restart (keystore/settings)."""
        rows = (
            client.table("connector_accounts")
            .select("provider,status")
            .eq("user_id", user_id)
            .in_("provider", [PROVIDER_AGENT_PLATFORM, PROVIDER_BAILEYS])
            .execute()
            .data
            or []
        )
        connected_providers = {r["provider"] for r in rows if r.get("status") == "connected"}
        if PROVIDER_AGENT_PLATFORM in connected_providers:
            key = keystore_mod.get_keystore().get_secret(keystore_mod.whatsapp_account(user_id))
            if key:
                try:
                    await self.connect_agent_platform(client, user_id, key)
                except Exception as exc:  # noqa: BLE001 - resume is best effort
                    log.warning("agent platform resume failed: %s", exc)
        if PROVIDER_BAILEYS in connected_providers:
            settings = BridgeSettings.from_dict(get_user_setting(client, user_id, "whatsapp_baileys", {}))
            try:
                await self.connect_baileys(client, user_id, settings)
            except Exception as exc:  # noqa: BLE001 - resume is best effort
                log.warning("baileys resume failed: %s", exc)

    async def stop_all(self) -> None:
        for name in list(self._transports):
            transport = self._transports.pop(name, None)
            if transport:
                await transport.stop()

    # -- status / send --------------------------------------------------------
    def status(self) -> dict:
        def _slot(name: str) -> dict:
            transport = self._transports.get(name)
            if not transport:
                return {"transport": name, "connected": False, "running": False}
            return {**transport.status(), "connected": True}

        return {
            "version": __version__,
            "agent_platform": _slot(AGENT_PLATFORM_NAME),
            "baileys": _slot(BAILEYS_NAME),
            "any_connected": bool(self._transports),
        }

    async def send(self, text: str, *, transport_name: str | None = None, to: str | None = None) -> dict:
        """Send via one (or the only) connected transport. Defaults to the last
        inbound peer — the Agent Platform only delivers to the creator anyway."""
        names = [transport_name] if transport_name else [AGENT_PLATFORM_NAME, BAILEYS_NAME]
        for name in names:
            transport = self._transports.get(name)
            if transport:
                peer = to or transport.last_peer
                if not peer:
                    raise RuntimeError(
                        "no destination known yet — message your agent on WhatsApp first, "
                        "or pass an explicit destination"
                    )
                message_id = await transport.send(peer, text)
                return {"transport": name, "peer": peer, "message_id": message_id}
        raise RuntimeError("no WhatsApp route is connected")


# ---------------------------------------------------------------------------
# Persistence + user_settings helpers (RLS-scoped, all sync — run via to_thread)
# ---------------------------------------------------------------------------
def persist_message(client, user_id: str, envelope: Envelope) -> None:
    """Record an inbound message: upsert the conversation, insert the row.

    Duplicate deliveries are absorbed by the unique `wa_message_id` (at-least-once
    is the platform's delivery semantics) — a unique-violation is a no-op.
    """
    occurred_at = (
        datetime.fromtimestamp(envelope.timestamp, tz=UTC).isoformat()
        if envelope.timestamp
        else datetime.now(UTC).isoformat()
    )
    conversation = (
        client.table("conversations")
        .upsert(
            {
                "user_id": user_id,
                "channel": "whatsapp",
                "transport": envelope.transport,
                "peer": envelope.peer,
            },
            on_conflict="user_id,channel,peer",
        )
        .execute()
        .data
        or []
    )
    conversation_id = conversation[0]["id"]
    client.table("messages").upsert(
        {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "direction": "inbound",
            "wa_message_id": envelope.message_id or None,
            "body": envelope.text,
            "media": envelope.media or {},
            "occurred_at": occurred_at,
        },
        on_conflict="wa_message_id",
    ).execute()


def get_user_setting(client, user_id: str, key: str, default=None):
    rows = (
        client.table("user_settings").select("settings").eq("user_id", user_id).limit(1).execute().data or []
    )
    if not rows:
        return default
    return (rows[0].get("settings") or {}).get(key, default)


def set_user_setting(client, user_id: str, key: str, value) -> None:
    rows = (
        client.table("user_settings").select("settings").eq("user_id", user_id).limit(1).execute().data or []
    )
    settings = (rows[0].get("settings") if rows else None) or {}
    settings[key] = value
    if rows:
        client.table("user_settings").update({"settings": settings}).eq("user_id", user_id).execute()
    else:
        client.table("user_settings").insert({"user_id": user_id, "settings": settings}).execute()


# Process-wide manager (the runtime serves one signed-in user at a time).
_manager: ConnectionManager | None = None


def get_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


async def shutdown_manager() -> None:
    global _manager
    if _manager is not None:
        await _manager.stop_all()
        _manager = None
