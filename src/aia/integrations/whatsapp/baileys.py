"""Baileys adapter — HTTP client for the Node WhatsApp sidecar.

The sidecar (services/whatsapp-gateway) owns the actual WhatsApp Web socket and
exposes a tiny REST API. Inbound messages are POSTed by the sidecar to the
Python gateway's /webhook/whatsapp endpoint; outbound goes through here.
"""
from __future__ import annotations

import httpx

from ...config import get_settings
from .base import WhatsAppProvider


class BaileysProvider(WhatsAppProvider):
    def __init__(self) -> None:
        self.base = get_settings().whatsapp_gateway_url.rstrip("/")

    async def send_text(self, to: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(f"{self.base}/send", json={"to": to, "text": text})
            r.raise_for_status()

    async def send_typing(self, to: str) -> None:
        async with httpx.AsyncClient(timeout=10) as http:
            await http.post(f"{self.base}/typing", json={"to": to})

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.get(f"{self.base}/health")
            return r.json()
