"""Auth-flow unit tests with mocked Supabase clients — no network."""
import pytest

from medot.supabase import auth as sa


class _FakeOAuth:
    def __init__(self, url):
        self._url = url

    def sign_in_with_oauth(self, options):
        assert options["provider"] == "google"
        assert options["options"]["redirect_to"].startswith("medot://")
        return type("R", (), {"url": self._url})()


class _FakeAuth:
    def __init__(self, url):
        self._url = url
        self.exchanged = None

    def sign_in_with_oauth(self, options):
        return _FakeOAuth(self._url).sign_in_with_oauth(options)

    def exchange_code_for_session(self, payload):
        self.exchanged = payload
        return type("S", (), {
            "user": type("U", (), {"id": "user-123"})(),
            "access_token": "at-1",
            "model_dump": lambda self, mode=None: {
                "access_token": "at-1",
                "user": {"id": "user-123"},
                "expires_at": 9999999999,
            },
        })()


@pytest.fixture()
def fake_client(monkeypatch, isolated_settings, mem_keystore):
    fake = _FakeAuth("https://supabase.example/authorize?provider=google")
    monkeypatch.setattr(sa, "_client", lambda: type("C", (), {"auth": fake})())
    return fake


async def test_start_builds_url_and_stores_verifier(fake_client, isolated_settings, mem_keystore):
    start = sa.start_google_signin(open_browser=False)
    assert start.authorize_url.startswith("https://supabase.example/authorize")
    assert mem_keystore.get_secret("supabase.pkce_verifier")


async def test_valid_callback_exchanges_and_persists_session(
    fake_client, isolated_settings, mem_keystore
):
    sa.start_google_signin(open_browser=False)
    url = "medot://auth/callback?code=the-code"
    session = sa.complete_signin(url)
    assert session["access_token"] == "at-1"
    assert fake_client.exchanged == {"auth_code": "the-code"}
    # Session blob persisted in the keystore + last-user remembered.
    assert mem_keystore.get_secret("supabase.session.user-123") is not None
    assert mem_keystore.get_secret("supabase.last_user") == "user-123"
    # Verifier consumed.
    assert mem_keystore.get_secret("supabase.pkce_verifier") is None


async def test_callback_without_pending_flow_rejected(isolated_settings, mem_keystore):
    with pytest.raises(RuntimeError, match="no pending sign-in"):
        sa.complete_signin("medot://auth/callback?code=x")


@pytest.mark.parametrize("bad_url", [
    "https://evil.example/callback?code=x",      # wrong scheme
    "medot://somewhere-else?code=x",             # wrong path
    "medot://auth/callback",                      # missing code
    "medot://auth/callback?error=access_denied",  # oauth error surfaced
])
async def test_malformed_callbacks_rejected(bad_url, fake_client):
    sa.start_google_signin(open_browser=False)
    with pytest.raises(ValueError):
        sa.validate_callback_url(bad_url)


async def test_load_session_roundtrip(isolated_settings, mem_keystore):
    assert sa.load_session() is None
    sa.remember_user("u9")
    mem_keystore.set_secret(sa.session_account("u9"), '{"user": {"id": "u9"}}')
    loaded = sa.load_session()
    assert loaded["user"]["id"] == "u9"
