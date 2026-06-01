from __future__ import annotations

from abc import ABC, abstractmethod


class VoiceProvider(ABC):
    @abstractmethod
    async def place_call(self, tenant_id: str, to: str, twiml_url: str) -> str:
        """Start an outbound call; returns a provider call id."""

    @abstractmethod
    def inbound_twiml(self, greeting: str, stream_url: str) -> str:
        """Return TwiML connecting the call audio to the realtime voice engine."""


def get_voice_provider(provider: str = "twilio") -> VoiceProvider:
    from .twilio_provider import TwilioVoiceProvider

    return TwilioVoiceProvider()
