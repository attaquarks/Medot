"""Event bus on Redis Streams.

Every external trigger becomes an event; agents are consumers. This decouples the
gateway (which only ingests) from the agents (which reason and act) and gives us
durability + at-least-once delivery via consumer groups.

Streams (topics):
  whatsapp.inbound    a WhatsApp message arrived
  email.received      a new/important email was detected by the email poller
  calendar.changed    a calendar event was created/updated/cancelled
  phone.inbound       an inbound call (or a finished call's transcript)
  health.update       the user logged a meal / weight / workout
  agent.outbound      an agent wants to send the user a WhatsApp message

Routing: the Business agent subscribes to {whatsapp.inbound[business], email.*,
calendar.*, phone.*}; the Health agent subscribes to {whatsapp.inbound[health],
health.update}. The gateway tags each inbound WhatsApp event with the target agent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Awaitable, Callable

import redis.asyncio as redis

from ..config import get_settings
from ..logging import get_logger

log = get_logger("events")


class Streams:
    WHATSAPP_INBOUND = "whatsapp.inbound"
    EMAIL_RECEIVED = "email.received"
    CALENDAR_CHANGED = "calendar.changed"
    PHONE_INBOUND = "phone.inbound"
    HEALTH_UPDATE = "health.update"
    AGENT_OUTBOUND = "agent.outbound"


@dataclass
class Event:
    type: str
    tenant_id: str
    payload: dict = field(default_factory=dict)

    def encode(self) -> dict[str, str]:
        return {"type": self.type, "tenant_id": self.tenant_id, "payload": json.dumps(self.payload)}

    @staticmethod
    def decode(fields: dict) -> "Event":
        return Event(
            type=fields["type"],
            tenant_id=fields.get("tenant_id", "default"),
            payload=json.loads(fields.get("payload", "{}")),
        )


Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._r = redis.from_url(get_settings().redis_url, decode_responses=True)

    async def publish(self, stream: str, event: Event) -> str:
        msg_id = await self._r.xadd(stream, event.encode())
        log.info("published", stream=stream, type=event.type)
        return msg_id

    async def consume(self, stream: str, group: str, handler: Handler) -> None:
        """Block forever, dispatching events to `handler`. At-least-once delivery.

        The consumer name is stable (= the group name), so after a restart the
        consumer first drains its own pending entries — messages that were
        delivered but not acked before the process died.
        """
        consumer = group
        try:
            await self._r.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError:
            pass  # group already exists

        await self._drain_own_pending(stream, group, consumer, handler)
        log.info("consumer_started", stream=stream, group=group, consumer=consumer)
        while True:
            resp = await self._r.xreadgroup(
                group, consumer, {stream: ">"}, count=10, block=5000
            )
            if not resp:
                continue
            for _stream, messages in resp:
                for msg_id, fields in messages:
                    try:
                        await handler(Event.decode(fields))
                        await self._r.xack(stream, group, msg_id)
                    except Exception as exc:  # keep the loop alive; stays pending until restart
                        log.error("handler_error", stream=stream, id=msg_id, error=str(exc))

    async def _drain_own_pending(
        self, stream: str, group: str, consumer: str, handler: Handler
    ) -> None:
        """Replay this consumer's un-acked messages (restart recovery).

        A message that fails again is acked anyway — one lost event after a
        repeat failure beats an unbounded crash loop.
        """
        try:
            while True:
                resp = await self._r.xreadgroup(group, consumer, {stream: "0"}, count=10)
                messages = resp[0][1] if resp else []
                if not messages:
                    break
                for msg_id, fields in messages:
                    if not fields:  # entry was deleted while pending
                        await self._r.xack(stream, group, msg_id)
                        continue
                    try:
                        await handler(Event.decode(fields))
                    except Exception as exc:
                        log.error("replayed_message_dropped", stream=stream, id=msg_id, error=str(exc))
                    await self._r.xack(stream, group, msg_id)
        except redis.ResponseError as exc:
            log.warning("pending_replay_failed", stream=stream, error=str(exc))


@lru_cache
def get_bus() -> EventBus:
    return EventBus()
