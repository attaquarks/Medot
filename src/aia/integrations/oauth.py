"""Generic OAuth 2.0 (authorization-code) manager.

One small, auditable flow handles every provider via a config table instead of a
per-provider SDK. Tokens are encrypted with the envelope cipher before they ever
touch Postgres (Requirement: no plaintext credentials).

Used by the onboarding wizard:
    url = manager.authorization_url("google", state)   # -> redirect the user
    await manager.exchange_code("google", code, tenant) # -> stores encrypted creds
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from ..config import get_settings
from ..db.base import session_scope
from ..db.models import Credential
from ..security.crypto import get_cipher

# Refresh when the token expires within this window (clock-skew safety).
REFRESH_SKEW = timedelta(seconds=120)


@dataclass(frozen=True)
class ProviderCfg:
    auth_url: str
    token_url: str
    scopes: list[str]


def _providers() -> dict[str, ProviderCfg]:
    return {
        "google": ProviderCfg(
            auth_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=[
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/calendar",
                "openid", "email",
            ],
        ),
        "microsoft": ProviderCfg(
            auth_url=f"https://login.microsoftonline.com/{get_settings().ms_tenant}/oauth2/v2.0/authorize",
            token_url=f"https://login.microsoftonline.com/{get_settings().ms_tenant}/oauth2/v2.0/token",
            scopes=["Mail.ReadWrite", "Mail.Send", "Calendars.ReadWrite", "offline_access", "openid", "email"],
        ),
    }


class OAuthManager:
    def __init__(self) -> None:
        self.s = get_settings()
        self.redirect_uri = f"{self.s.public_base_url}/oauth/callback"

    def _client(self, provider: str) -> tuple[str, str]:
        if provider == "google":
            return self.s.google_client_id or "", self.s.google_client_secret or ""
        if provider == "microsoft":
            return self.s.ms_client_id or "", self.s.ms_client_secret or ""
        raise ValueError(f"unknown provider {provider}")

    def authorization_url(self, provider: str, state: str) -> str:
        cfg = _providers()[provider]
        client_id, _ = self._client(provider)
        from urllib.parse import urlencode

        q = urlencode({
            "client_id": client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(cfg.scopes),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        })
        return f"{cfg.auth_url}?{q}"

    async def exchange_code(self, provider: str, code: str, tenant_id: str) -> str:
        cfg = _providers()[provider]
        client_id, client_secret = self._client(provider)
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(cfg.token_url, data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            })
            resp.raise_for_status()
            token = resp.json()
        return await self._store(provider, tenant_id, token, cfg.scopes)

    async def get_access_token(
        self, tenant_id: str, provider: str, *, http: httpx.AsyncClient | None = None
    ) -> str:
        """Return a valid access token, refreshing via refresh_token when stale.

        The refreshed token replaces the stored row in place (the refresh_token
        is kept when the provider does not rotate it). Raises RuntimeError when
        the provider was never connected or the token is expired with no
        refresh_token — the user must re-run onboarding in that case.
        """
        token, expires_at = await self._load(tenant_id, provider)
        if token is None:
            raise RuntimeError(f"{provider} account not connected — run onboarding.")
        if expires_at is not None and datetime.now(timezone.utc) - REFRESH_SKEW < expires_at:
            return token["access_token"]

        refresh = token.get("refresh_token")
        if not refresh:
            raise RuntimeError(
                f"{provider} token expired and no refresh_token stored — reconnect via onboarding."
            )
        cfg = _providers()[provider]
        client_id, client_secret = self._client(provider)
        own = http is None
        http = http or httpx.AsyncClient(timeout=30)
        try:
            resp = await http.post(cfg.token_url, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            new_token = resp.json()
        finally:
            if own:
                await http.aclose()
        merged = {**token, **new_token}  # keep the old refresh_token if not rotated
        merged.setdefault("refresh_token", refresh)
        await self._update(tenant_id, provider, merged)
        return merged["access_token"]

    async def _store(self, provider: str, tenant_id: str, token: dict, scopes: list[str]) -> str:
        cipher = get_cipher()
        blob = cipher.encrypt(json.dumps(token))
        expires_at = _expires_at(token)
        async with session_scope() as s:
            cred = Credential(
                tenant_id=tenant_id,
                provider=provider,
                account_label=_token_email(token),
                encrypted_blob=blob,
                scopes=" ".join(scopes),
                expires_at=expires_at,
            )
            s.add(cred)
            await s.flush()
            return cred.id

    async def _update(self, tenant_id: str, provider: str, token: dict) -> None:
        """Replace the latest credential row's blob + expiry after a refresh."""
        async with session_scope() as s:
            row = await self._latest(s, tenant_id, provider)
            if row:
                row.encrypted_blob = get_cipher().encrypt(json.dumps(token))
                row.expires_at = _expires_at(token)
                row.account_label = _token_email(token) or row.account_label

    @staticmethod
    async def _latest(s, tenant_id: str, provider: str) -> Credential | None:
        return (
            await s.execute(
                select(Credential)
                .where(Credential.tenant_id == tenant_id, Credential.provider == provider)
                .order_by(Credential.created_at.desc())
            )
        ).scalars().first()

    @staticmethod
    async def _load(tenant_id: str, provider: str) -> tuple[dict | None, datetime | None]:
        """Decrypt and return the stored token dict + row expiry for a provider."""
        async with session_scope() as s:
            row = await OAuthManager._latest(s, tenant_id, provider)
            if not row:
                return None, None
            exp = row.expires_at
            if exp is not None and exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)  # SQLite drops the offset
            return json.loads(get_cipher().decrypt(row.encrypted_blob)), exp

    @staticmethod
    async def load_token(tenant_id: str, provider: str) -> dict | None:
        """Decrypt and return the stored token dict for a provider (or None)."""
        token, _ = await OAuthManager._load(tenant_id, provider)
        return token


def _expires_at(token: dict) -> datetime | None:
    if "expires_in" not in token:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(token["expires_in"]))


def _token_email(token: dict) -> str:
    """Best-effort account label: the `email` claim inside id_token, if present."""
    raw = token.get("id_token")
    if not raw:
        return ""
    try:
        payload_b64 = raw.split(".")[1]
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)))
        return payload.get("email", "") or ""
    except Exception:
        return ""
