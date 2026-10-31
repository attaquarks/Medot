"""Shared fixtures for Medot runtime tests."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from medot.localstore.keystore import InMemoryKeystore


class _MemBackend(InMemoryKeystore):
    """InMemoryKeystore already matches the keyring backend interface."""


@pytest.fixture()
def mem_keystore(monkeypatch):
    """Replace the process keystore with an in-memory double."""
    ks = KeystoreDouble()
    monkeypatch.setattr("medot.localstore.keystore.get_keystore", lambda: ks)
    return ks


class KeystoreDouble:
    """Keystore interface backed by memory (set/get/delete secret)."""

    def __init__(self):
        self._backend = _MemBackend()

    def set_secret(self, account: str, secret: str) -> None:
        self._backend.set_password("medot", f"medot:{account}", secret)

    def get_secret(self, account: str) -> str | None:
        return self._backend.get_password("medot", f"medot:{account}")

    def delete_secret(self, account: str) -> None:
        self._backend.delete_password("medot", f"medot:{account}")


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    """Fresh settings per test: isolated data dir, local-stack Supabase if up."""
    from medot.config import get_settings

    monkeypatch.setenv("MEDOT_DATA_DIR", str(tmp_path / "medot"))
    monkeypatch.setenv("MEDOT_SUPABASE_URL", os.environ.get("MEDOT_TEST_SUPABASE_URL", ""))
    monkeypatch.setenv("MEDOT_SUPABASE_PUBLISHABLE_KEY", os.environ.get("MEDOT_TEST_SUPABASE_KEY", ""))
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def supabase_available() -> bool:
    url = os.environ.get("MEDOT_TEST_SUPABASE_URL")
    if not url:
        return False
    import httpx

    try:
        httpx.get(f"{url.rstrip('/')}/auth/v1/health", timeout=2)
        return True
    except Exception:
        return False
