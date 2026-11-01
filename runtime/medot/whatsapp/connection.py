"""WhatsApp Agent Platform connection.

The user links the Medot agent in WhatsApp's Agent Manager, copies the API
key WhatsApp generates, and pastes it into Medot Desktop. The key is stored
in the OS keystore and the connection is recorded as a `connector_accounts`
row (provider `whatsapp_agent_platform`).

The messaging wire-protocol calls against the Agent Platform are wired in the
transport adapter once the platform's API surface is captured (the user has
access to Agent Manager; docs are not public). Until then this module owns
credential storage and connection state — the parts that never change.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..localstore import keystore as keystore_mod

PROVIDER = "whatsapp_agent_platform"
MIN_KEY_LENGTH = 16


@dataclass
class ConnectionStatus:
    connected: bool
    connected_at: str | None = None

    def as_dict(self) -> dict:
        return {
            "provider": PROVIDER,
            "connected": self.connected,
            "connected_at": self.connected_at,
        }


def validate_api_key(api_key: str) -> str:
    key = (api_key or "").strip()
    if len(key) < MIN_KEY_LENGTH:
        raise ValueError(
            f"that doesn't look like a WhatsApp agent API key (expected at least {MIN_KEY_LENGTH} characters)"
        )
    return key


def connect(client, user_id: str, api_key: str) -> ConnectionStatus:
    """Store the API key in the OS keystore and record the connection.

    `client` is a Supabase client running as the authenticated user (RLS
    scopes every write to that user).
    """
    key = validate_api_key(api_key)
    credential_ref = keystore_mod.whatsapp_account(user_id)
    keystore_mod.get_keystore().set_secret(credential_ref, key)

    existing = (
        client.table("connector_accounts")
        .select("id")
        .eq("user_id", user_id)
        .eq("provider", PROVIDER)
        .limit(1)
        .execute()
        .data
        or []
    )
    row = {
        "user_id": user_id,
        "provider": PROVIDER,
        "account_label": "Medot agent",
        "credential_ref": credential_ref,
        "status": "connected",
    }
    if existing:
        client.table("connector_accounts").update(row).eq("id", existing[0]["id"]).execute()
    else:
        client.table("connector_accounts").insert(row).execute()
    return status(client, user_id)


def status(client, user_id: str) -> ConnectionStatus:
    rows = (
        client.table("connector_accounts")
        .select("status,connected_at")
        .eq("user_id", user_id)
        .eq("provider", PROVIDER)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows or rows[0]["status"] != "connected":
        return ConnectionStatus(connected=False)
    return ConnectionStatus(connected=True, connected_at=rows[0].get("connected_at"))


def disconnect(client, user_id: str) -> None:
    credential_ref = keystore_mod.whatsapp_account(user_id)
    keystore_mod.get_keystore().delete_secret(credential_ref)
    client.table("connector_accounts").update({"status": "revoked"}).eq(
        "user_id", user_id
    ).eq("provider", PROVIDER).execute()
