"""Twilio voice adapter.

Architecture for live calls:
  Caller <-> Twilio PSTN <-> Media Streams (websocket) <-> voice engine
  (Deepgram Voice Agent or OpenAI Realtime) <-> Business agent tools.

`inbound_twiml` returns markup that bridges call audio to our media-stream
websocket; the engine transcribes, runs the agent turn, and speaks the reply.
Outbound calls are placed with the REST client. Transcripts + summaries land in
business.call_logs and important calls raise an escalation event.
"""
from __future__ import annotations

from ...config import get_settings
from .base import VoiceProvider


class TwilioVoiceProvider(VoiceProvider):
    def __init__(self) -> None:
        self.s = get_settings()

    async def place_call(self, tenant_id: str, to: str, twiml_url: str) -> str:
        from twilio.rest import Client  # imported lazily; optional dependency at runtime

        if not (self.s.twilio_account_sid and self.s.twilio_auth_token):
            raise RuntimeError("Twilio not configured — add credentials in onboarding.")
        client = Client(self.s.twilio_account_sid, self.s.twilio_auth_token)
        call = client.calls.create(to=to, from_=self.s.twilio_phone_number, url=twiml_url)
        return call.sid

    def inbound_twiml(self, greeting: str, stream_url: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f"<Say>{greeting}</Say>"
            f'<Connect><Stream url="{stream_url}"/></Connect>'
            "</Response>"
        )
