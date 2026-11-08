"""Connector registry (M7): catalog, CRUD, keystore secrets, Me. grants."""
import pytest
from test_whatsapp_manager import FakeClient

from medot.connectors import registry
from medot.localstore.keystore import InMemoryKeystore, Keystore


def _keystore():
    return Keystore(InMemoryKeystore())


def test_catalog_has_claude_style_entries():
    keys = [c["key"] for c in registry.CATALOG]
    assert {"github", "gmail", "google_calendar", "google_drive", "slack", "notion", "custom"} <= set(keys)
    github = next(c for c in registry.CATALOG if c["key"] == "github")
    assert github["url"].startswith("https://") and github["auth_header_name"]


def test_create_connector_secrets_and_me_grant():
    client = FakeClient()
    client.tables["identities"] = [{"id": "me-1", "user_id": "u1", "slug": "me"}]
    ks = _keystore()

    created = registry.create_connector(
        client, "u1", ks,
        provider="github", account_label="My GitHub", url="https://api.githubcopilot.com/mcp/",
        auth_header_name="Authorization", auth_header_value="ghp_secret",
    )
    row = client.tables["connector_accounts"][0]
    assert row["url"].startswith("https://") and row["enabled"] is True
    assert ks.get_secret(registry.credential_account("u1", created["id"])) == "ghp_secret"
    assert "ghp_secret" not in str(client.tables)  # secrets never in the DB
    grants = client.tables["identity_connector_grants"]
    assert grants[0]["identity_id"] == "me-1" and grants[0]["can_write"] is True

    with pytest.raises(ValueError, match="URL"):
        registry.create_connector(client, "u1", ks, provider="x", account_label="", url="ftp://nope")


def test_update_and_delete_connector():
    client = FakeClient()
    ks = _keystore()
    created = registry.create_connector(client, "u1", ks, provider="custom", account_label="X", url="https://a/mcp")
    cid = created["id"]

    updated = registry.update_connector(client, "u1", ks, cid, enabled=False)
    assert updated["enabled"] is False

    registry.update_connector(client, "u1", ks, cid, auth_header_value="tok-1")
    assert ks.get_secret(registry.credential_account("u1", cid)) == "tok-1"
    registry.update_connector(client, "u1", ks, cid, auth_header_value="")
    assert ks.get_secret(registry.credential_account("u1", cid)) is None

    registry.delete_connector(client, "u1", ks, cid)
    assert client.tables["connector_accounts"] == []  # the row is gone (the endpoint 404s on a repeat)
    assert registry.delete_connector(client, "u1", ks, cid) is False
