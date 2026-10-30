"""Business agent worker entrypoint:  python -m aia.agents.business.service

Subscribes to its event streams, runs the email poller, and schedules the
proactive morning brief. Runs forever; the event bus provides at-least-once
delivery via consumer groups.
"""
from __future__ import annotations

import asyncio

from ...config import get_settings
from ...events.bus import Streams, get_bus
from ...integrations.email.poller import EmailPoller
from ...integrations.oauth import OAuthManager
from ...logging import configure_logging, get_logger
from .. import principal as principal_mod
from ..scheduler import run_daily
from . import workflow

log = get_logger("business.service")
GROUP = "business"

DAILY_BRIEF_LOCAL_TIME = (8, 0)  # 08:00 in AIA_TIMEZONE


async def _send_daily_brief() -> None:
    target = await principal_mod.principal_whatsapp()
    if not target:
        log.warning("daily_brief_skipped_no_principal")
        return
    await workflow.daily_summary(get_settings().tenant_id, target)


async def _maybe_email_poller() -> None:
    """Run the poller only when an email account is actually connected."""
    s = get_settings()
    provider_cred = "google" if s.email_provider == "gmail" else "microsoft"
    try:
        token = await OAuthManager.load_token(s.tenant_id, provider_cred)
    except Exception:
        token = None
    if not token:
        log.info("email_poller_disabled", reason=f"no connected {provider_cred} account")
        return
    await EmailPoller(s.tenant_id).run_forever()


async def _run() -> None:
    bus = get_bus()
    log.info("business_agent_starting")
    await asyncio.gather(
        # Per-agent inbound stream: the gateway routes each WhatsApp message to
        # exactly one agent so the two never both answer the same message.
        bus.consume(f"{Streams.WHATSAPP_INBOUND}.business", GROUP, workflow.on_whatsapp),
        bus.consume(Streams.EMAIL_RECEIVED, GROUP, workflow.on_email),
        bus.consume(Streams.PHONE_INBOUND, GROUP, workflow.on_phone),
        _maybe_email_poller(),
        run_daily("daily_brief", *DAILY_BRIEF_LOCAL_TIME, _send_daily_brief),
    )


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
