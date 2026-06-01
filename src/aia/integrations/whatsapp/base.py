from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

from ...config import get_settings


class WhatsAppProvider(ABC):
    """Minimal transport contract the agents rely on."""

    @abstractmethod
    async def send_text(self, to: str, text: str) -> None: ...

    @abstractmethod
    async def send_typing(self, to: str) -> None: ...

    @abstractmethod
    async def health(self) -> dict: ...


@lru_cache
def get_whatsapp() -> WhatsAppProvider:
    provider = get_settings().whatsapp_provider
    if provider == "cloud":
        from .cloud_api import CloudApiProvider

        return CloudApiProvider()
    from .baileys import BaileysProvider

    return BaileysProvider()
