"""WhatsApp Agent Platform connection: key storage, connection state."""
import pytest

from medot.whatsapp import connection as wa


class _FakeQuery:
    """Minimal chainable supabase-py double for one table."""

    def __init__(self, rows):
        self._rows = rows
        self._result = rows

    def select(self, *_a):
        return self

    def insert(self, row):
        stored = dict(row)
        stored.setdefault("id", f"row-{len(self._rows) + 1}")  # DB default gen_random_uuid()
        self._rows.append(stored)
        self._last = [dict(stored)]
        return self

    def update(self, patch):
        self._pending = patch
        return self

    def eq(self, col, val):
        if hasattr(self, "_pending"):
            for row in self._rows:
                if row.get(col) == val:
                    row.update(self._pending)
            self._last = [dict(self._pending)]
        else:
            self._result = [r for r in self._rows if r.get(col) == val]
        return self

    def limit(self, _n):
        return self

    def execute(self):
        if hasattr(self, "_pending"):
            self._pending = None
            return type("R", (), {"data": self._last})()
        return type("R", (), {"data": list(self._result)})()


class _FakeClient:
    def __init__(self):
        self.tables: dict[str, list] = {}

    def table(self, name):
        return _FakeQuery(self.tables.setdefault(name, []))


@pytest.fixture()
def fake_client():
    return _FakeClient()


async def test_connect_stores_key_and_records_connection(fake_client, mem_keystore):
    status = wa.connect(fake_client, "user-1", "wapia-key-1234567890abcdef")
    assert status.connected is True
    # Key lives in the keystore, never in the database.
    assert mem_keystore.get_secret("whatsapp.user-1") == "wapia-key-1234567890abcdef"
    row = fake_client.tables["connector_accounts"][0]
    assert row["provider"] == "whatsapp_agent_platform"
    assert row["status"] == "connected"
    assert "key" not in str(row) or "wapia" not in str(row["credential_ref"])


async def test_connect_rejects_short_keys(fake_client, mem_keystore):
    with pytest.raises(ValueError, match="doesn't look like"):
        wa.connect(fake_client, "user-1", "short")
    assert fake_client.tables.get("connector_accounts") in (None, [])


async def test_connect_twice_updates_not_duplicates(fake_client, mem_keystore):
    wa.connect(fake_client, "user-1", "wapia-key-1234567890abcdef")
    wa.connect(fake_client, "user-1", "wapia-key-0987654321fedcba")
    rows = fake_client.tables["connector_accounts"]
    assert len(rows) == 1
    assert mem_keystore.get_secret("whatsapp.user-1") == "wapia-key-0987654321fedcba"


async def test_status_disconnected_when_no_row(fake_client):
    assert wa.status(fake_client, "nobody").connected is False


async def test_disconnect_revokes_and_clears_key(fake_client, mem_keystore):
    wa.connect(fake_client, "user-1", "wapia-key-1234567890abcdef")
    wa.disconnect(fake_client, "user-1")
    assert mem_keystore.get_secret("whatsapp.user-1") is None
    assert wa.status(fake_client, "user-1").connected is False
