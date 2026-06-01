"""Phone/voice abstraction. Twilio for telephony; a voice engine (Deepgram Voice
Agent or OpenAI Realtime) handles STT<->LLM<->TTS during a live call."""
from .base import VoiceProvider, get_voice_provider

__all__ = ["VoiceProvider", "get_voice_provider"]
