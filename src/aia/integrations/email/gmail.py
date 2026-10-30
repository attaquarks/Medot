"""Gmail adapter via the REST API using the stored, encrypted OAuth token.

Kept dependency-light (httpx + Bearer token) so the flow is auditable. Token
refresh is handled by `_access_token` (refreshes when expired).
"""
from __future__ import annotations

import base64
from email.message import EmailMessage as MimeMessage

import httpx

from ..oauth import OAuthManager
from .base import EmailMessage, EmailProvider

API = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailProvider(EmailProvider):
    async def _access_token(self, tenant_id: str) -> str:
        # Auto-refreshes via refresh_token when the stored token has expired.
        return await OAuthManager().get_access_token(tenant_id, "google")

    async def list_recent(self, tenant_id: str, *, max_results: int = 20) -> list[EmailMessage]:
        tok = await self._access_token(tenant_id)
        headers = {"Authorization": f"Bearer {tok}"}
        async with httpx.AsyncClient(timeout=30) as http:
            ids = (await http.get(
                f"{API}/messages", headers=headers,
                params={"maxResults": max_results, "q": "in:inbox"},
            )).json().get("messages", [])
            out: list[EmailMessage] = []
            for m in ids:
                msg = (await http.get(
                    f"{API}/messages/{m['id']}", headers=headers,
                    params={"format": "metadata", "metadataHeaders": ["From", "Subject"]},
                )).json()
                hdrs = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                out.append(EmailMessage(
                    external_id=m["id"],
                    sender=hdrs.get("From", ""),
                    subject=hdrs.get("Subject", ""),
                    snippet=msg.get("snippet", ""),
                ))
            return out

    async def get_body(self, tenant_id: str, external_id: str) -> str:
        tok = await self._access_token(tenant_id)
        async with httpx.AsyncClient(timeout=30) as http:
            msg = (await http.get(
                f"{API}/messages/{external_id}", headers={"Authorization": f"Bearer {tok}"},
                params={"format": "full"},
            )).json()
        return _extract_plain_text(msg)

    async def send(self, tenant_id: str, to: str, subject: str, body: str) -> str:
        tok = await self._access_token(tenant_id)
        raw = _build_raw(to, subject, body)
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(
                f"{API}/messages/send", headers={"Authorization": f"Bearer {tok}"},
                json={"raw": raw},
            )
            r.raise_for_status()
            return r.json()["id"]

    async def create_draft(self, tenant_id: str, to: str, subject: str, body: str) -> str:
        tok = await self._access_token(tenant_id)
        raw = _build_raw(to, subject, body)
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(
                f"{API}/drafts", headers={"Authorization": f"Bearer {tok}"},
                json={"message": {"raw": raw}},
            )
            r.raise_for_status()
            return r.json()["id"]


def _build_raw(to: str, subject: str, body: str) -> str:
    mime = MimeMessage()
    mime["To"] = to
    mime["Subject"] = subject
    mime.set_content(body)
    return base64.urlsafe_b64encode(mime.as_bytes()).decode()


def _extract_plain_text(msg: dict) -> str:
    payload = msg.get("payload", {})
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(errors="ignore")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode(errors="ignore")
    return msg.get("snippet", "")
