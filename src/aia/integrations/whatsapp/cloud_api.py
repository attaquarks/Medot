"""Meta WhatsApp Business Cloud API adapter (official, compliant).

Notes vs Baileys:
  * Requires a Meta Business account + a phone number registered to the API.
  * Free-form replies are only allowed inside the 24-hour customer service window;
    proactive messages outside it must use pre-approved *template* messages.
    `send_template` is provided for that case.
"""
from __future__ import annotations

import httpx

from ...config import get_settings
from .base import WhatsAppProvider

GRAPH = "https://graph.facebook.com/v20.0"


class CloudApiProvider(WhatsAppProvider):
    def __init__(self) -> None:
        s = get_settings()
        self.token = s.whatsapp_cloud_token or ""
        self.phone_id = s.whatsapp_cloud_phone_id or ""

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def send_text(self, to: str, text: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(f"{GRAPH}/{self.phone_id}/messages", json=payload, headers=self._headers)
            r.raise_for_status()

    async def send_template(self, to: str, template: str, lang: str = "en_US", components: list | None = None) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {"name": template, "language": {"code": lang}, "components": components or []},
        }
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(f"{GRAPH}/{self.phone_id}/messages", json=payload, headers=self._headers)
            r.raise_for_status()

    async def send_typing(self, to: str) -> None:
        # Cloud API has no typing indicator; no-op to satisfy the interface.
        return None

    async def health(self) -> dict:
        return {"provider": "cloud", "configured": bool(self.token and self.phone_id)}
