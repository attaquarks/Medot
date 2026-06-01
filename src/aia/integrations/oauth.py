"""Generic OAuth 2.0 (authorization-code) manager.

One small, auditable flow handles every provider via a config table instead of a
per-provider SDK. Tokens are encrypted with the envelope cipher before they ever
touch Postgres (Requirement: no plaintext credentials).

Used by the onboarding wizard:
    url = manager.authorization_url("google", state)   # -> redirect the user
    await manager.exchange_code("google", code, tenant) # -> stores encrypted creds
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx

from ..config import get_settings
from ..db.base import session_scope
from ..db.models import Credential
from ..security.crypto import get_cipher


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

    async def _store(self, provider: str, tenant_id: str, token: dict, scopes: list[str]) -> str:
        cipher = get_cipher()
        blob = cipher.encrypt(json.dumps(token))
        expires_at = None
        if "expires_in" in token:
            expires_at = time.time() + int(token["expires_in"])
        async with session_scope() as s:
            cred = Credential(
                tenant_id=tenant_id,
                provider=provider,
                account_label=token.get("email", ""),
                encrypted_blob=blob,
                scopes=" ".join(scopes),
            )
            s.add(cred)
            await s.flush()
            return cred.id

    @staticmethod
    async def load_token(tenant_id: str, provider: str) -> dict | None:
        """Decrypt and return the stored token dict for a provider (or None)."""
        from sqlalchemy import select

        async with session_scope() as s:
            row = (
                await s.execute(
                    select(Credential)
                    .where(Credential.tenant_id == tenant_id, Credential.provider == provider)
                    .order_by(Credential.created_at.desc())
                )
            ).scalars().first()
            if not row:
                return None
            return json.loads(get_cipher().decrypt(row.encrypted_blob))
