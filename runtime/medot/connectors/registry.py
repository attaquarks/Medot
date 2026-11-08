"""Connector registry (M7, doc 08 §5/§7): a catalog of popular connectors
(capability descriptors, code-owned) plus user-added custom MCP servers —
one click for the catalog, paste-a-URL for custom, exactly like Claude's
connector UI. Rows live in connector_accounts; header secrets live in the
OS keystore; per-identity grants seed for Me. on connect.
"""
from __future__ import annotations

# The directory the console shows first — the same surface Claude/ChatGPT put
# on their Connectors screens. url may be empty when there is no canonical
# hosted endpoint; the user pastes one. auth_hint is plain language.
CATALOG: list[dict] = [
    {"key": "github", "title": "GitHub", "blurb": "Issues, PRs, repos, code search.",
     "url": "https://api.githubcopilot.com/mcp/",
     "auth_header_name": "Authorization", "auth_hint": "Paste a GitHub personal access token."},
    {"key": "notion", "title": "Notion", "blurb": "Search and edit your workspace pages.",
     "url": "", "auth_header_name": "Authorization",
     "auth_hint": "Paste your Notion MCP endpoint and an integration token."},
    {"key": "linear", "title": "Linear", "blurb": "Issues, projects, cycles.",
     "url": "", "auth_header_name": "Authorization",
     "auth_hint": "Paste your Linear MCP endpoint and API key."},
    {"key": "slack", "title": "Slack", "blurb": "Channels, messages, summaries.",
     "url": "", "auth_header_name": "", "auth_hint": "Paste a Slack MCP server URL."},
    {"key": "gmail", "title": "Gmail", "blurb": "Read, draft and search mail.",
     "url": "", "auth_header_name": "", "auth_hint": "Paste a Gmail MCP server URL."},
    {"key": "google_calendar", "title": "Google Calendar", "blurb": "Schedule and recall events.",
     "url": "", "auth_header_name": "", "auth_hint": "Paste a Calendar MCP server URL."},
    {"key": "google_drive", "title": "Google Drive", "blurb": "Search and read your files.",
     "url": "", "auth_header_name": "", "auth_hint": "Paste a Drive MCP server URL."},
    {"key": "custom", "title": "Custom connector", "blurb": "Any MCP server — paste its URL.",
     "url": "", "auth_header_name": "", "auth_hint": "Most servers need no auth; some take a Bearer token."},
]


def credential_account(user_id: str, connector_id: str) -> str:
    return f"connectors.{user_id}.{connector_id}"


def list_connectors(client, user_id: str) -> list[dict]:
    return (
        client.table("connector_accounts")
        .select("id,provider,account_label,url,auth_header_name,enabled,status,connected_at")
        .eq("user_id", user_id)
        .order("connected_at")
        .execute()
        .data
        or []
    )


def create_connector(
    client,
    user_id: str,
    keystore,
    *,
    provider: str,
    account_label: str,
    url: str,
    auth_header_name: str | None = None,
    auth_header_value: str | None = None,
) -> dict:
    """One row per connected server; Me. gets its connector grant here."""
    if not (url or "").strip():
        raise ValueError("paste the connector's MCP server URL")
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("the connector URL must start with http(s)://")
    row = {
        "user_id": user_id,
        "provider": provider or "custom",
        "account_label": (account_label or "").strip() or provider or "connector",
        "url": url,
        "auth_header_name": (auth_header_name or "").strip() or None,
        "enabled": True,
        "status": "connected",
    }
    inserted = client.table("connector_accounts").insert(row).execute().data or []
    if not inserted:
        raise ValueError("could not save the connector")
    connector = inserted[0]
    if auth_header_value:
        keystore.set_secret(credential_account(user_id, connector["id"]), auth_header_value.strip())
    me = (
        client.table("identities")
        .select("id")
        .eq("user_id", user_id)
        .eq("slug", "me")
        .limit(1)
        .execute()
        .data
        or []
    )
    if me:
        client.table("identity_connector_grants").insert(
            {
                "user_id": user_id,
                "identity_id": me[0]["id"],
                "connector_account_id": connector["id"],
                "can_read": True,
                "can_write": True,
            }
        ).execute()
    return connector


def update_connector(
    client,
    user_id: str,
    keystore,
    connector_id: str,
    *,
    account_label: str | None = None,
    url: str | None = None,
    auth_header_name: str | None = None,
    auth_header_value: str | None = None,
    enabled: bool | None = None,
) -> dict | None:
    patch: dict = {}
    if account_label is not None:
        patch["account_label"] = account_label.strip()
    if url is not None:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("the connector URL must start with http(s)://")
        patch["url"] = url
    if auth_header_name is not None:
        patch["auth_header_name"] = auth_header_name.strip() or None
    if enabled is not None:
        patch["enabled"] = enabled
    if auth_header_value is not None:
        if auth_header_value.strip():
            keystore.set_secret(credential_account(user_id, connector_id), auth_header_value.strip())
        else:
            keystore.delete_secret(credential_account(user_id, connector_id))
    if not patch and auth_header_value is None:
        raise ValueError("nothing to update")
    rows = (
        client.table("connector_accounts")
        .update(patch)
        .eq("id", connector_id)
        .eq("user_id", user_id)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def delete_connector(client, user_id: str, keystore, connector_id: str) -> bool:
    keystore.delete_secret(credential_account(user_id, connector_id))
    rows = (
        client.table("connector_accounts")
        .delete()
        .eq("id", connector_id)
        .eq("user_id", user_id)
        .execute()
        .data
        or []
    )
    return bool(rows)


def header_value(keystore, user_id: str, connector_id: str) -> str | None:
    return keystore.get_secret(credential_account(user_id, connector_id))
