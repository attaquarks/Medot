"""Provider discovery + profiles: unit tests (mocked HTTP, fake Supabase)."""
import httpx
import pytest

from medot.providers import profiles as profiles_mod
from medot.providers.discovery import discover_models, litellm_target


class _FakeAsyncClient:
    """httpx.AsyncClient double returning canned responses per URL substring."""

    def __init__(self, routes, **_kw):
        self._routes = routes  # {substring: (status, json)}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, params=None):
        for substring, (status, payload) in self._routes.items():
            if substring in url:
                return httpx.Response(status, json=payload, request=httpx.Request("GET", url))
        return httpx.Response(404, json={}, request=httpx.Request("GET", url))


def _patch_http(monkeypatch, routes):
    monkeypatch.setattr(
        "medot.providers.discovery.httpx.AsyncClient",
        lambda **kw: _FakeAsyncClient(routes, **kw),
    )


@pytest.mark.parametrize(
    "provider,routes,expected",
    [
        (
            "openai_compatible",
            {"/models": (200, {"data": [{"id": "gpt-x"}, {"id": "gpt-a"}]})},
            ["gpt-a", "gpt-x"],
        ),
        ("ollama", {"/api/tags": (200, {"models": [{"name": "llama3:8b"}]})}, ["llama3:8b"]),
        ("anthropic", {"/v1/models": (200, {"data": [{"id": "claude-x"}]})}, ["claude-x"]),
        ("google", {"/v1beta/models": (200, {"models": [{"name": "models/gemini-y"}]})}, ["gemini-y"]),
    ],
)
async def test_discover_models_parses_each_provider(monkeypatch, provider, routes, expected):
    _patch_http(monkeypatch, routes)
    assert await discover_models(provider, None, "k") == expected


async def test_discover_models_rejects_bad_key(monkeypatch):
    _patch_http(monkeypatch, {"/models": (401, {"error": {}})})
    with pytest.raises(ValueError, match="key was rejected"):
        await discover_models("openai_compatible", None, "bad")


async def test_discover_models_unreachable(monkeypatch):
    class _Broken:
        def __init__(self, **kw):
            raise httpx.ConnectError("no")

    monkeypatch.setattr("medot.providers.discovery.httpx.AsyncClient", _Broken)
    with pytest.raises(ValueError, match="couldn't reach the provider"):
        await discover_models("openai_compatible", None, "k")


def test_litellm_target_mapping():
    assert litellm_target("openai_compatible", "m", None) == ("openai/m", "https://api.openai.com/v1")
    assert litellm_target("ollama", "m", "http://x:11434") == ("ollama_chat/m", "http://x:11434")
    assert litellm_target("anthropic", "m", None) == ("anthropic/m", None)
    assert litellm_target("google", "m", None) == ("gemini/m", None)
    with pytest.raises(ValueError, match="unknown provider"):
        litellm_target("nope", "m", None)


# ---------------------------------------------------------------------------
# profiles CRUD (fake Supabase double + in-memory keystore)
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
        stored.setdefault("id", "prof-1")
        self._rows.append(stored)
        self._last = [dict(stored)]
        return self

    def update(self, patch):
        self._pending = patch
        return self

    def delete(self):
        self._deleting = True
        self._rows[:] = [r for r in self._rows if True]
        return self

    def eq(self, col, val):
        if self._pending is not None:
            for row in self._rows:
                if row.get(col) == val:
                    row.update(self._pending)
            self._last = [dict(self._pending)]
        elif getattr(self, "_deleting", False):
            self._rows[:] = [r for r in self._rows if r.get(col) != val]
        else:
            self._result = [r for r in self._rows if r.get(col) == val]
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def execute(self):
        if self._pending is not None:
            self._pending = None
            return type("R", (), {"data": self._last or []})()
        return type("R", (), {"data": list(self._result)})()


class FakeClient:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return FakeQuery(self.tables.setdefault(name, []))


@pytest.fixture()
def fake_client():
    return FakeClient()


def _save(client, keystore, **over):
    args = dict(
        profile_id=None,
        name="Main",
        purpose="chat",
        provider="openai_compatible",
        model="gpt-x",
        api_base=None,
        api_key="sk-test-123",
    )
    args.update(over)
    return profiles_mod.save_profile(client, "user-1", keystore, **args)


def test_save_profile_stores_key_in_keystore_not_db(fake_client, mem_keystore):
    saved = _save(fake_client, mem_keystore)
    assert saved["name"] == "Main"
    assert fake_client.tables["model_profiles"][0]["model"] == "gpt-x"
    # the key lives in the keystore, and no table row carries it
    assert mem_keystore.get_secret(f"providers.user-1.{saved['id']}") == "sk-test-123"
    assert "sk-test" not in str(fake_client.tables)


def test_save_profile_requires_name_and_model(fake_client, mem_keystore):
    with pytest.raises(ValueError, match="name"):
        _save(fake_client, mem_keystore, name="  ")
    with pytest.raises(ValueError, match="pick a model"):
        _save(fake_client, mem_keystore, model="")
    with pytest.raises(ValueError, match="purpose"):
        _save(fake_client, mem_keystore, purpose="vibes")


def test_update_profile_rotates_key(fake_client, mem_keystore):
    saved = _save(fake_client, mem_keystore)
    _save(fake_client, mem_keystore, profile_id=saved["id"], api_key="sk-new-456")
    assert mem_keystore.get_secret(f"providers.user-1.{saved['id']}") == "sk-new-456"
    assert len(fake_client.tables["model_profiles"]) == 1


def test_delete_profile_clears_keystore(fake_client, mem_keystore):
    saved = _save(fake_client, mem_keystore)
    profiles_mod.delete_profile(fake_client, "user-1", mem_keystore, saved["id"])
    assert mem_keystore.get_secret(f"providers.user-1.{saved['id']}") is None
    assert fake_client.tables["model_profiles"] == []


async def test_verify_profile_calls_model_with_keystore_key(fake_client, mem_keystore, monkeypatch):
    saved = _save(fake_client, mem_keystore)
    captured = {}

    async def fake_acompletion(**kw):
        captured.update(kw)
        msg = type("M", (), {"content": "OK"})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice]})()

    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    result = await profiles_mod.verify_profile(fake_client, "user-1", mem_keystore, saved["id"])
    assert result["ok"] is True
    assert result["sample"] == "OK"
    assert captured["model"] == "openai/gpt-x"
    assert captured["api_key"] == "sk-test-123"
    assert captured["messages"][0]["content"].startswith("Reply")


async def test_verify_profile_without_key_is_a_clear_error(fake_client, mem_keystore):
    saved = _save(fake_client, mem_keystore, api_key=None)
    with pytest.raises(ValueError, match="no key stored"):
        await profiles_mod.verify_profile(fake_client, "user-1", mem_keystore, saved["id"])
