"""Business agent class + event-driven workflow handlers.

Event subscriptions (see aia.events.bus.Streams):
  whatsapp.inbound  -> converse with a client/contact, then reply on WhatsApp
  email.received    -> triage (categorise + urgency), draft if useful, escalate if urgent
  calendar.changed  -> note the change, notify the principal if it affects them
  phone.inbound     -> summarise the call transcript, escalate if important
"""
from __future__ import annotations

from ...events.bus import Event
from ...integrations.whatsapp import get_whatsapp
from ...llm.router import get_router
from ...logging import get_logger
from ..base import BaseAgent
from .prompts import SYSTEM_PROMPT
from .tools import registry

log = get_logger("business.workflow")


class BusinessAgent(BaseAgent):
    name = "business"
    system_prompt = SYSTEM_PROMPT

    def __init__(self) -> None:
        super().__init__(registry)


agent = BusinessAgent()


async def on_whatsapp(event: Event) -> None:
    peer = event.payload["peer"]
    text = event.payload.get("text", "")
    wa = get_whatsapp()
    try:  # typing is best-effort; a down sidecar must not drop the reply
        await wa.send_typing(peer)
    except Exception as exc:
        log.warning("send_typing_failed", peer=peer, error=str(exc))
    reply = await agent.handle_message(event.tenant_id, peer, text)
    await wa.send_text(peer, reply)


async def on_email(event: Event) -> None:
    """Triage a freshly-arrived email. The poller publishes id+sender+subject+snippet."""
    p = event.payload
    prompt = (
        "Triage this email. Return one line: <category> | <urgency low|normal|high|urgent> | "
        "<one-sentence summary>.\n\n"
        f"From: {p.get('sender')}\nSubject: {p.get('subject')}\n{p.get('snippet')}"
    )
    verdict = await get_router().complete([{"role": "user", "content": prompt}], complexity="auto")
    log.info("email_triaged", verdict=verdict)
    if "urgent" in verdict.lower():
        await get_whatsapp().send_text(
            event.payload.get("principal", p.get("sender")),
            f"🔔 Urgent email from {p.get('sender')}: {p.get('subject')}\n{verdict}",
        )


async def on_phone(event: Event) -> None:
    transcript = event.payload.get("transcript", "")
    summary = await get_router().complete(
        [{"role": "user", "content": f"Summarise this call in 2 lines and flag if it needs the principal:\n{transcript}"}],
        complexity="hard",
    )
    log.info("call_summarised", summary=summary)


async def daily_summary(tenant_id: str, principal_wa: str) -> None:
    """Proactive morning brief. Triggered by the scheduler (see service.main)."""
    brief = await agent.handle_message(
        tenant_id, principal_wa,
        "Give me my morning brief: today's meetings, urgent emails, and open follow-ups.",
    )
    await get_whatsapp().send_text(principal_wa, f"☀️ Morning brief\n\n{brief}")
