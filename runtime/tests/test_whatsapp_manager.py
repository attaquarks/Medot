"""WhatsApp transport manager: dedupe, persistence, status, send routing."""
import pytest

from medot.whatsapp import connection as wa_conn
from medot.whatsapp import manager as wa
from medot.whatsapp.baileys import BridgeSettings


# ---------------------------------------------------------------------------
# Supabase double (chainable, mimics supabase-py)
# ---------------------------------------------------------------------------
class FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._result = rows
        self._pending = None
        self._upsert_row = None
        self._on_conflict = None

    def select(self, *_a):
        return self

    def insert(self, row):
        stored = dict(row)
        stored.setdefault("id", f"row-{len(self._rows) + 1}")
        self._rows.append(stored)
        self._last = [dict(stored)]
        return self

    def upsert(self, row, on_conflict=None):
        self._upsert_row = dict(row)
        self._on_conflict = on_conflict
        return self

    def update(self, patch):
        self._pending = patch
        return self

    def eq(self, col, val):
        if self._upsert_row is not None:
            # upsert + eq is not a real supabase-py pattern; support the common path
            pass
        if hasattr(self, "_pending") and self._pending is not None:
            for row in self._rows:
                if row.get(col) == val:
                    row.update(self._pending)
            self._last = [dict(self._pending)]
        else:
            self._result = [r for r in self._rows if r.get(col) == val]
        return self

    def in_(self, col, vals):
        self._result = [r for r in self._rows if r.get(col) in vals]
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def execute(self):
        if self._upsert_row is not None:
            key_cols = [c.strip() for c in (self._on_conflict or "").split(",") if c.strip()]
            for row in self._rows:
                if all(row.get(c) == self._upsert_row.get(c) for c in key_cols):
                    row.update(self._upsert_row)
                    self._last = [dict(row)]
                    return self._wrap([dict(row)])
            stored = dict(self._upsert_row)
            stored.setdefault("id", f"row-{len(self._rows) + 1}")
            self._rows.append(stored)
            self._last = [dict(stored)]
            return self._wrap([dict(stored)])
        if self._pending is not None:
            self._pending = None
            return self._wrap(self._last or [])
        return self._wrap(list(self._result))

    def _wrap(self, data):
        return type("R", (), {"data": data})()


class FakeClient:
    def __init__(self):
        self.tables: dict[str, list] = {}

    def table(self, name):
        return FakeQuery(self.tables.setdefault(name, []))


@pytest.fixture()
def fake_client():
    return FakeClient()


# ---------------------------------------------------------------------------
# Envelope handling + persistence
# ---------------------------------------------------------------------------
def _envelope(**over) -> wa.Envelope:
    base = {
        "transport": "agent_platform",
        "message_id": "wamid.1",
        "peer": "user:50972923564215",
        "chat": "user:50972923564215",
        "sender": "user:50972923564215",
        "text": "hello me.",
        "timestamp": 1736844652,
    }
    base.update(over)
    return wa.Envelope(**base)


async def test_handle_dedupes_by_transport_and_id(fake_client):
    mgr = wa.ConnectionManager()
    mgr._client = fake_client
    mgr._user_id = "user-1"
    await mgr._handle(_envelope())
    await mgr._handle(_envelope())
    assert len(fake_client.tables["messages"]) == 1
    assert mgr.inbound_count == 1


async def test_persist_creates_conversation_and_message(fake_client):
    wa.persist_message(fake_client, "user-1", _envelope())
    conversations = fake_client.tables["conversations"]
    assert len(conversations) == 1
    assert conversations[0]["peer"] == "user:50972923564215"
    assert conversations[0]["transport"] == "agent_platform"
    messages = fake_client.tables["messages"]
    assert len(messages) == 1
    assert messages[0]["body"] == "hello me."
    # replay: same wa_message_id does not duplicate
    wa.persist_message(fake_client, "user-1", _envelope())
    assert len(fake_client.tables["messages"]) == 1


async def test_persist_baileys_uses_baileys_transport(fake_client):
    wa.persist_message(fake_client, "user-1", _envelope(transport="baileys", peer="15551234567"))
    conv = fake_client.tables["conversations"][0]
    assert conv["transport"] == "baileys"


async def test_on_message_hook_runs_before_persistence(fake_client):
    seen = []

    async def hook(env):
        seen.append(env.message_id)

    mgr = wa.ConnectionManager()
    mgr.on_message = hook
    mgr._client = fake_client
    mgr._user_id = "a"
    await mgr._handle(_envelope())
    assert seen == ["wamid.1"]


# ---------------------------------------------------------------------------
# Status + send routing
# ---------------------------------------------------------------------------
class FakeTransport:
    name = "agent_platform"
    provider = wa_conn.PROVIDER

    def __init__(self, error=None):
        self.error = error
        self.last_peer = "user:509"
        self.sent = []

    async def stop(self):
        pass

    async def send(self, peer, text, reply_to=None):
        self.sent.append((peer, text))
        return "wamid.FAKE"

    def status(self) -> dict:
        return {"transport": self.name, "running": True, "error": self.error}


async def test_status_aggregates_both_slots():
    mgr = wa.ConnectionManager()
    s = mgr.status()
    assert s["agent_platform"]["connected"] is False
    assert s["baileys"]["connected"] is False
    assert s["any_connected"] is False

    mgr._transports["agent_platform"] = FakeTransport()
    s = mgr.status()
    assert s["agent_platform"]["connected"] is True
    assert s["any_connected"] is True


async def test_send_prefers_requested_transport_then_first_connected(fake_client):
    mgr = wa.ConnectionManager()
    fake_ap = FakeTransport()
    fake_ba = FakeTransport()
    mgr._transports = {"agent_platform": fake_ap, "baileys": fake_ba}

    out = await mgr.send("hi", transport_name="baileys")
    assert out["transport"] == "baileys"
    assert fake_ba.sent == [("user:509", "hi")]

    mgr2 = wa.ConnectionManager()
    mgr2._transports = {"baileys": FakeTransport()}
    out = await mgr2.send("yo")
    assert out["transport"] == "baileys"

    with pytest.raises(RuntimeError, match="no WhatsApp route is connected"):
        await wa.ConnectionManager().send("x")


async def test_send_without_known_peer_is_a_clear_error():
    mgr = wa.ConnectionManager()
    t = FakeTransport()
    t.last_peer = None
    mgr._transports["agent_platform"] = t
    with pytest.raises(RuntimeError, match="no destination known"):
        await mgr.send("hello?")


# ---------------------------------------------------------------------------
# Baileys settings
# ---------------------------------------------------------------------------
def test_bridge_settings_self_mode_clears_allowlist():
    s = BridgeSettings(mode="self", allowed_users=["1555"])
    s.validate()
    assert s.allowed_users == [] and s.allow_all is False


def test_bridge_settings_bot_mode_requires_allowlist():
    with pytest.raises(ValueError, match="allowed phone number"):
        BridgeSettings(mode="bot").validate()
    s = BridgeSettings(mode="bot", allowed_users=["15551234567"])
    s.validate()
    assert s.group_policy == "pairing"
    with pytest.raises(ValueError, match="group_policy"):
        BridgeSettings(mode="self", group_policy="weird").validate()


def test_bridge_settings_roundtrip():
    s = BridgeSettings(mode="bot", allowed_users=["15551234567"], group_policy="open", require_mention=True)
    assert BridgeSettings.from_dict(s.to_dict()) == s
