"""Calendar `gaps` maths + the Graph calendar / Notion / Todoist REST providers.

All HTTP is served by httpx.MockTransport injected through each provider's
`_client()` seam; OAuth tokens are stubbed.
"""
from datetime import datetime, timezone
import json

import httpx
import pytest

from aia.config import get_settings
from aia.integrations.calendar.base import gaps

UTC = timezone.utc


# ------------------------------- gaps() ---------------------------------------
def test_gaps_splits_around_busy_blocks():
    start = datetime(2026, 10, 27, 8, 0, tzinfo=UTC)
    end = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
    busy = [
        (datetime(2026, 10, 27, 9, 0, tzinfo=UTC), datetime(2026, 10, 27, 9, 30, tzinfo=UTC)),
        (datetime(2026, 10, 27, 10, 0, tzinfo=UTC), datetime(2026, 10, 27, 11, 0, tzinfo=UTC)),
    ]
    slots = gaps(start, end, busy, 30)
    assert [(s.starts_at, s.ends_at) for s in slots] == [
        (datetime(2026, 10, 27, 8, 0, tzinfo=UTC), datetime(2026, 10, 27, 9, 0, tzinfo=UTC)),
        (datetime(2026, 10, 27, 9, 30, tzinfo=UTC), datetime(2026, 10, 27, 10, 0, tzinfo=UTC)),
        (datetime(2026, 10, 27, 11, 0, tzinfo=UTC), datetime(2026, 10, 27, 12, 0, tzinfo=UTC)),
    ]


def test_gaps_drops_windows_too_short_and_overlaps():
    start = datetime(2026, 10, 27, 8, 0, tzinfo=UTC)
    end = datetime(2026, 10, 27, 10, 0, tzinfo=UTC)
    busy = [
        (datetime(2026, 10, 27, 8, 0, tzinfo=UTC), datetime(2026, 10, 27, 9, 45, tzinfo=UTC)),
        (datetime(2026, 10, 27, 9, 0, tzinfo=UTC), datetime(2026, 10, 27, 9, 50, tzinfo=UTC)),  # overlap
    ]
    slots = gaps(start, end, busy, 30)
    # Only 10 free minutes remain after the merged block -> nothing fits.
    assert slots == []


@pytest.fixture()
def provider_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "ntn-test")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db123")
    monkeypatch.setenv("TODOIST_TOKEN", "tdt-test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _with_transport(provider, handler, base_url: str = ""):
    """Bind MockTransport-backed clients to a provider's _client() seam.

    Returns the list of opened clients so the test can close them all —
    each call to _client() must return a fresh (never-closed) client.
    """
    transport = httpx.MockTransport(handler)
    opened: list[httpx.AsyncClient] = []

    def make() -> httpx.AsyncClient:
        c = httpx.AsyncClient(base_url=base_url, transport=transport)
        opened.append(c)
        return c

    provider._client = make
    return opened


async def _close_all(clients: list) -> None:
    for c in clients:
        await c.aclose()


# --------------------------- Graph calendar -----------------------------------
@pytest.fixture()
def graph_provider(monkeypatch):
    from aia.integrations.calendar.graph import GraphCalendarProvider

    async def fake_token(self, tenant_id: str) -> str:
        return "fake-ms-token"

    monkeypatch.setattr(GraphCalendarProvider, "_token", fake_token)
    return GraphCalendarProvider()


async def test_graph_list_events_maps_fields(graph_provider):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1.0/me/calendarview"
        assert "fake-ms-token" in request.headers["authorization"]
        return httpx.Response(200, json={"value": [{
            "id": "ev1", "subject": "Standup",
            "start": {"dateTime": "2026-10-27T09:00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2026-10-27T09:15:00", "timeZone": "UTC"},
            "attendees": [{"emailAddress": {"address": "a@x.com"}}],
        }]})

    clients = _with_transport(graph_provider, handler)
    events = await graph_provider.list_events(
        "t1", datetime(2026, 10, 27, tzinfo=UTC), datetime(2026, 10, 28, tzinfo=UTC)
    )
    await _close_all(clients)

    assert events[0]["id"] == "ev1"
    assert events[0]["summary"] == "Standup"
    assert events[0]["attendees"] == ["a@x.com"]


async def test_graph_create_event_returns_id(graph_provider):
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.read().decode())
        return httpx.Response(201, json={"id": "new-ev"})

    clients = _with_transport(graph_provider, handler)
    eid = await graph_provider.create_event(
        "t1", "Lunch",
        datetime(2026, 10, 27, 12, 0, tzinfo=UTC),
        datetime(2026, 10, 27, 13, 0, tzinfo=UTC),
        ["b@x.com"],
    )
    await _close_all(clients)

    assert eid == "new-ev"
    body = json.loads(bodies[0])
    assert body["subject"] == "Lunch"
    assert body["start"] == {"dateTime": "2026-10-27T12:00:00", "timeZone": "UTC"}
    assert body["attendees"] == [{"emailAddress": {"address": "b@x.com"}}]


async def test_graph_free_slots_computes_windows(graph_provider):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": [{
            "id": "ev1", "subject": "Busy",
            "start": {"dateTime": "2026-10-27T09:00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2026-10-27T09:30:00", "timeZone": "UTC"},
            "attendees": [],
        }]})

    clients = _with_transport(graph_provider, handler)
    slots = await graph_provider.free_slots(
        "t1",
        datetime(2026, 10, 27, 8, 0, tzinfo=UTC),
        datetime(2026, 10, 27, 10, 0, tzinfo=UTC),
        30,
    )
    await _close_all(clients)

    assert [(s.starts_at, s.ends_at) for s in slots] == [
        (datetime(2026, 10, 27, 8, 0, tzinfo=UTC), datetime(2026, 10, 27, 9, 0, tzinfo=UTC)),
        (datetime(2026, 10, 27, 9, 30, tzinfo=UTC), datetime(2026, 10, 27, 10, 0, tzinfo=UTC)),
    ]


# ------------------------------- Notion ---------------------------------------
async def test_notion_add_list_complete(provider_env):
    from aia.integrations.tasks.notion import NotionTaskProvider

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path.endswith("/pages"):
            return httpx.Response(200, json={"id": "page-1"})
        if request.url.path.endswith("/query"):
            return httpx.Response(200, json={"results": [{
                "id": "page-1",
                "properties": {"Name": {"title": [{"plain_text": "Call Bob"}]},
                               "Done": {"checkbox": False}},
            }]})
        return httpx.Response(200, json={})

    p = NotionTaskProvider()
    clients = _with_transport(p, handler, base_url="https://api.notion.com/v1/")
    tid = await p.add("t1", "Call Bob", datetime(2026, 10, 28, 10, 0, tzinfo=UTC))
    rows = await p.list_open("t1")
    await p.complete("t1", tid)
    await _close_all(clients)

    assert tid == "page-1"
    assert rows == [{"id": "page-1", "title": "Call Bob", "status": "open"}]
    assert any(m == "PATCH" for m, _ in seen)


# ------------------------------ Todoist ---------------------------------------
async def test_todoist_add_list_complete(provider_env):
    from aia.integrations.tasks.todoist import TodoistTaskProvider

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url)))
        if request.method == "POST" and request.url.path.endswith("/tasks"):
            return httpx.Response(200, json={"id": "td-1", "content": "Send invoice"})
        if request.method == "GET" and request.url.path.endswith("/tasks"):
            return httpx.Response(200, json=[{"id": "td-1", "content": "Send invoice"}])
        return httpx.Response(204)

    p = TodoistTaskProvider()
    clients = _with_transport(p, handler, base_url="https://api.todoist.com/rest/v2/")
    tid = await p.add("t1", "Send invoice")
    rows = await p.list_open("t1")
    await p.complete("t1", tid)
    await _close_all(clients)

    assert tid == "td-1"
    assert rows == [{"id": "td-1", "title": "Send invoice", "status": "open"}]
    assert any(m == "POST" and u.endswith("/close") for m, u in seen)
