"""OS keystore access (Windows Credential Manager / macOS Keychain / Linux
Secret Service) — the ONLY store for secrets in Medot: AI provider keys,
WhatsApp session secrets, OAuth refresh tokens, Supabase session blobs.

A nullable `backend` is injectable for tests. On hosts with no usable keyring
service, `get_keyring()` returns a fail backend — callers get a clear error
instead of silent plaintext fallback.
"""
from __future__ import annotations

import os
from functools import lru_cache

_SERVICE = "medot"


class Keystore:
    def __init__(self, backend=None):
        if backend is None:
            import keyring

            backend = keyring.get_keyring()
        self._backend = backend

    def _qualified(self, account: str) -> str:
        return f"{_SERVICE}:{account}"

    def set_secret(self, account: str, secret: str) -> None:
        self._backend.set_password(_SERVICE, self._qualified(account), secret)

    def get_secret(self, account: str) -> str | None:
        return self._backend.get_password(_SERVICE, self._qualified(account))

    def delete_secret(self, account: str) -> None:
        try:
            self._backend.delete_password(_SERVICE, self._qualified(account))
        except Exception:  # noqa: BLE001, S110 - already absent is fine
            pass


class InMemoryKeystore:
    """Test/CI double with the same interface."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def set_password(self, service: str, account: str, password: str) -> None:
        self._store[account] = password

    def get_password(self, service: str, account: str) -> str | None:
        return self._store.get(account)

    def delete_password(self, service: str, account: str) -> None:
        self._store.pop(account, None)


@lru_cache
def get_keystore() -> Keystore:
    if os.environ.get("MEDOT_KEYSTORE") == "memory":  # test-only: CI e2e has no OS keystore
        return Keystore(InMemoryKeystore())
    return Keystore()


# Well-known account names (namespaced per user where applicable).
def session_account(user_id: str) -> str:
    return f"supabase.session.{user_id}"


def provider_account(user_id: str, profile_name: str) -> str:
    return f"providers.{user_id}.{profile_name}"


def whatsapp_account(user_id: str) -> str:
    return f"whatsapp.{user_id}"
