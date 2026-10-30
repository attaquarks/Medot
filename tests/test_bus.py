"""Event bus integration: pending messages are reclaimed after a consumer dies.

Requires a reachable Redis; skips silently otherwise (CI/dev without the stack).
"""
import asyncio
import uuid

import pytest
import redis as redis_sync

from aia.config import get_settings
from aia.events.bus import Event, EventBus


def _redis_available(url: str) -> bool:
    try:
        client = redis_sync.Redis.from_url(url, socket_connect_timeout=1)
        client.ping()
        client.close()
        return True
    except Exception:
        return False


@pytest.fixture()
def bus_url(monkeypatch):
    url = "redis://localhost:6378/0"
    if not _redis_available(url):
        pytest.skip("no local Redis for integration test")
    monkeypatch.setenv("REDIS_URL", url)
    get_settings.cache_clear()
    yield url
    get_settings.cache_clear()


async def test_pending_message_is_replayed_and_processed(bus_url):
    stream = f"test.replay.{uuid.uuid4().hex[:8]}"
    bus = EventBus()
    await bus._r.xgroup_create(stream, "g", id="0", mkstream=True)
    await bus.publish(
        stream, Event(type="test.msg", tenant_id="t1", payload={"n": 1})
    )
    # A dead consumer (same stable name the loop will use) reads the message
    # but never acks -> it stays pending in this consumer's PEL.
    await bus._r.xreadgroup("g", "g", {stream: ">"}, count=10)

    got: list[Event] = []

    async def handler(ev: Event) -> None:
        got.append(ev)

    task = asyncio.create_task(bus.consume(stream, "g", handler))
    try:
        for _ in range(20):
            if got:
                break
            await asyncio.sleep(0.25)
    finally:
        task.cancel()
        with __import__("contextlib").suppress(asyncio.CancelledError, Exception):
            await task
        await bus._r.delete(stream)
        await bus._r.aclose()

    assert len(got) == 1 and got[0].payload == {"n": 1}
