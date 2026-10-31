"""Unit tests: paths, keystore, config — no external services."""
from medot.localstore.keystore import (
    InMemoryKeystore,
    Keystore,
    provider_account,
    session_account,
)
from medot.localstore.paths import ensure_layout, workspace_root


def test_workspace_layout_creates_all_dirs(tmp_path):
    dirs = ensure_layout(tmp_path)
    for name in ("workspace", "documents", "state", "checkpoints", "logs", "browser_profiles"):
        assert dirs[name].exists(), name
    assert str(dirs["checkpoints"]).endswith("checkpoints")


def test_workspace_root_override():
    from pathlib import Path

    assert workspace_root("X:/custom") == Path("X:/custom")


def test_keystore_roundtrip_with_inmemory_backend():
    ks = Keystore(backend=InMemoryKeystore())
    account = session_account("user-1")
    assert ks.get_secret(account) is None
    ks.set_secret(account, '{"access_token": "abc"}')
    assert ks.get_secret(account) == '{"access_token": "abc"}'
    ks.delete_secret(account)
    assert ks.get_secret(account) is None


def test_keystore_namespacing():
    ks = Keystore(backend=InMemoryKeystore())
    ks.set_secret(session_account("u1"), "a")
    ks.set_secret(provider_account("u1", "OpenAI"), "b")
    assert ks.get_secret(session_account("u1")) == "a"
    assert ks.get_secret(provider_account("u1", "OpenAI")) == "b"
    # Secrets of different users/accounts never collide.
    assert ks.get_secret(session_account("u2")) is None


def test_delete_missing_secret_is_noop():
    ks = Keystore(backend=InMemoryKeystore())
    ks.delete_secret("never-existed")  # must not raise


def test_runtime_settings_reject_privileged_keys():
    # AC4 guard at the type level: the settings model has no service-role field.
    from medot.config import Settings

    fields = Settings.model_fields.keys()
    assert not any("service" in f or "secret" in f or "privileged" in f for f in fields)
