"""Microsoft Graph email adapter (Outlook / Microsoft 365).

Same interface as Gmail; calls https://graph.microsoft.com/v1.0/me/messages with
the stored Microsoft OAuth token. Endpoints stubbed with the exact contract to
fill in — mirror the Gmail adapter's structure.
"""
from __future__ import annotations

import httpx

from ..oauth import OAuthManager
from .base import EmailMessage, EmailProvider

API = "https://graph.microsoft.com/v1.0/me"


class GraphEmailProvider(EmailProvider):
    async def _token(self, tenant_id: str) -> str:
        tok = await OAuthManager.load_token(tenant_id, "microsoft")
        if not tok:
            raise RuntimeError("Microsoft account not connected — run onboarding.")
        return tok["access_token"]

    async def list_recent(self, tenant_id: str, *, max_results: int = 20) -> list[EmailMessage]:
        tok = await self._token(tenant_id)
        async with httpx.AsyncClient(timeout=30) as http:
            data = (await http.get(
                f"{API}/messages", headers={"Authorization": f"Bearer {tok}"},
                params={"$top": max_results, "$select": "id,from,subject,bodyPreview,receivedDateTime"},
            )).json()
        return [
            EmailMessage(
                external_id=m["id"],
                sender=m.get("from", {}).get("emailAddress", {}).get("address", ""),
                subject=m.get("subject", ""),
                snippet=m.get("bodyPreview", ""),
            )
            for m in data.get("value", [])
        ]

    async def get_body(self, tenant_id: str, external_id: str) -> str:
        tok = await self._token(tenant_id)
        async with httpx.AsyncClient(timeout=30) as http:
            m = (await http.get(
                f"{API}/messages/{external_id}", headers={"Authorization": f"Bearer {tok}"},
            )).json()
        return m.get("body", {}).get("content", m.get("bodyPreview", ""))

    async def send(self, tenant_id: str, to: str, subject: str, body: str) -> str:
        tok = await self._token(tenant_id)
        payload = {"message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }}
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(f"{API}/sendMail", headers={"Authorization": f"Bearer {tok}"}, json=payload)
            r.raise_for_status()
        return "sent"

    async def create_draft(self, tenant_id: str, to: str, subject: str, body: str) -> str:
        tok = await self._token(tenant_id)
        payload = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(f"{API}/messages", headers={"Authorization": f"Bearer {tok}"}, json=payload)
            r.raise_for_status()
            return r.json()["id"]
