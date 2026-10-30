"""OAuth manager: expires_at persistence, account label, and token refresh.

DB-backed tests run on a temp SQLite file (the `db_env` fixture in conftest)
so no Postgres is needed. The refresh HTTP call is injected via MockTransport.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("db_env")


def _jwt(payload: dict) -> str:
    """Minimal unsigned JWT (only the payload matters for label extraction)."""
    seg = base64.urlsafe_b64encode(json.dumps(payload).encode()).strip(b"=")
    return f"x.{seg.decode()}.y"


async def _credentials():
    from sqlalchemy import select

    from aia.db.base import session_scope
    from aia.db.models import Credential

    async with session_scope() as s:
        return (await s.execute(select(Credential))).scalars().all()


@pytest.mark.usefixtures("db_env")
async def test_store_persists_expires_at_and_email_label():
    from aia.integrations.oauth import OAuthManager

    token = {
        "access_token": "at-1",
        "refresh_token": "rt-1",
        "expires_in": 3600,
        "id_token": _jwt({"email": "owner@example.com"}),
    }
    await OAuthManager()._store("google", "t1", token, ["scope"])
    (row,) = await _credentials()
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)  # SQLite drops the offset
    assert exp > datetime.now(timezone.utc) + timedelta(minutes=55)
    assert row.account_label == "owner@example.com"


@pytest.mark.usefixtures("db_env")
async def test_get_access_token_returns_valid_token_without_refreshing():
    from aia.integrations.oauth import OAuthManager

    await OAuthManager()._store(
        "google", "t1", {"access_token": "fresh", "refresh_token": "rt", "expires_in": 3600}, []
    )
    tok = await OAuthManager().get_access_token("t1", "google")
    assert tok == "fresh"


@pytest.mark.usefixtures("db_env")
async def test_get_access_token_refreshes_when_expired_and_updates_row():
    from aia.integrations.oauth import OAuthManager

    # expires_in < 0 -> stored token is already expired.
    await OAuthManager()._store(
        "google", "t1", {"access_token": "stale", "refresh_token": "rt-1", "expires_in": -300}, []
    )

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.read().decode())
        return httpx.Response(200, json={"access_token": "brand-new", "expires_in": 3600})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        tok = await OAuthManager().get_access_token("t1", "google", http=http)

    assert tok == "brand-new"
    assert len(calls) == 1 and "grant_type=refresh_token" in calls[0]
    # The stored row now carries the new token and a future expiry.
    (row,) = await _credentials()
    assert json.loads(
        __import__("aia.security.crypto", fromlist=["get_cipher"]).get_cipher().decrypt(row.encrypted_blob)
    )["access_token"] == "brand-new"
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    assert exp > datetime.now(timezone.utc) + timedelta(minutes=55)


@pytest.mark.usefixtures("db_env")
async def test_get_access_token_raises_when_not_connected():
    from aia.integrations.oauth import OAuthManager

    with pytest.raises(RuntimeError, match="onboarding"):
        await OAuthManager().get_access_token("t1", "google")


@pytest.mark.usefixtures("db_env")
async def test_refresh_keeps_old_refresh_token_if_provider_omits_it():
    from aia.integrations.oauth import OAuthManager

    await OAuthManager()._store(
        "google", "t1", {"access_token": "stale", "refresh_token": "keep-me", "expires_in": -300}, []
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "new2", "expires_in": 3600})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await OAuthManager().get_access_token("t1", "google", http=http)

    (row,) = await _credentials()
    blob = json.loads(
        __import__("aia.security.crypto", fromlist=["get_cipher"]).get_cipher().decrypt(row.encrypted_blob)
    )
    assert blob["refresh_token"] == "keep-me"
