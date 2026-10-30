"""Health agent class + workflow handlers.

Event subscriptions:
  whatsapp.inbound.health -> converse: log meals/weight/workouts, coach, report
  health.update           -> a structured log arrived from another surface (e.g. a
                             future mobile widget); acknowledge + nudge on WhatsApp

Proactive: `daily_accountability` and `weekly_checkin` are fired by the scheduler.
"""
from __future__ import annotations

from ...events.bus import Event
from ...integrations.whatsapp import get_whatsapp
from ...logging import get_logger
from ..base import BaseAgent
from .prompts import SYSTEM_PROMPT
from .tools import registry

log = get_logger("health.workflow")


class HealthAgent(BaseAgent):
    name = "health"
    system_prompt = SYSTEM_PROMPT

    def __init__(self) -> None:
        super().__init__(registry)


agent = HealthAgent()


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


async def on_health_update(event: Event) -> None:
    peer = event.payload.get("peer", "")
    if not peer:
        log.warning("health_update_missing_peer")
        return
    note = event.payload.get("note", "")
    reply = await agent.handle_message(event.tenant_id, peer, note)
    await get_whatsapp().send_text(peer, reply)


async def daily_accountability(tenant_id: str, client_wa: str) -> None:
    msg = await agent.handle_message(
        tenant_id, client_wa,
        "End-of-day check-in: how did today go vs my calorie & protein targets? "
        "Be encouraging and give me one tip for tomorrow.",
    )
    await get_whatsapp().send_text(client_wa, f"🌙 Daily check-in\n\n{msg}")


async def weekly_checkin(tenant_id: str, client_wa: str) -> None:
    msg = await agent.handle_message(
        tenant_id, client_wa, "Give me my weekly progress report with the weight trend.",
    )
    await get_whatsapp().send_text(client_wa, f"📊 Weekly report\n\n{msg}")
