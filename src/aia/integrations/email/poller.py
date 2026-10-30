"""Background email poller: turns a mailbox into `email.received` events.

The Business agent subscribes to that stream for triage/escalation. New
messages are deduped by external id in a Redis set; the very first poll only
records what's already in the inbox (no flood of "new" events for old mail).
"""
from __future__ import annotations

import asyncio

import redis.asyncio as redis

from ...agents.principal import principal_whatsapp
from ...config import get_settings
from ...events.bus import Event, Streams, get_bus
from ...logging import get_logger
from .base import EmailMessage, get_email_provider

log = get_logger("email.poller")


def new_messages(seen: set[str], messages: list[EmailMessage]) -> list[EmailMessage]:
    """Messages whose external_id has never been polled before."""
    return [m for m in messages if m.external_id and m.external_id not in seen]


class EmailPoller:
    def __init__(self, tenant_id: str | None = None, interval: int | None = None):
        s = get_settings()
        self.tenant_id = tenant_id or s.tenant_id
        self.interval = interval or s.email_poll_seconds
        self._r = redis.from_url(s.redis_url, decode_responses=True)
        self._seen_key = f"aia:{self.tenant_id}:email:seen"
        self._bootstrapped = False

    async def run_forever(self) -> None:
        await asyncio.sleep(10)  # let the stack settle before the first poll
        while True:
            try:
                n = await self.poll_once()
                if n:
                    log.info("email_events_published", count=n)
            except Exception as exc:
                log.warning("email_poll_failed", error=str(exc))
            await asyncio.sleep(self.interval)

    async def poll_once(self) -> int:
        provider = get_email_provider(get_settings().email_provider)
        messages = await provider.list_recent(self.tenant_id, max_results=10)
        seen = set(await self._r.smembers(self._seen_key))
        fresh = new_messages(seen, messages)

        if not self._bootstrapped:
            # First poll: record the existing inbox without publishing events.
            self._bootstrapped = True
            await self._mark_seen(messages)
            return 0
        if not fresh:
            return 0

        principal = await principal_whatsapp(self.tenant_id)
        bus = get_bus()
        for m in fresh:
            await bus.publish(
                Streams.EMAIL_RECEIVED,
                Event(
                    type="email.received",
                    tenant_id=self.tenant_id,
                    payload={
                        "external_id": m.external_id,
                        "sender": m.sender,
                        "subject": m.subject,
                        "snippet": m.snippet,
                        "principal": principal or "",
                    },
                ),
            )
        await self._mark_seen(fresh)
        return len(fresh)

    async def _mark_seen(self, messages: list[EmailMessage]) -> None:
        ids = [m.external_id for m in messages if m.external_id]
        if not ids:
            return
        await self._r.sadd(self._seen_key, *ids)
        await self._r.expire(self._seen_key, 60 * 60 * 24 * 14)
