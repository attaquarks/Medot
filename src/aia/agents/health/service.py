"""Health agent worker entrypoint:  python -m aia.agents.health.service

Subscribes to its event streams and schedules the proactive daily check-in and
weekly report. Runs forever.
"""
from __future__ import annotations

import asyncio

from ...config import get_settings
from ...events.bus import Streams, get_bus
from ...logging import configure_logging, get_logger
from .. import principal as principal_mod
from ..scheduler import MONDAY, run_daily, run_weekly
from . import workflow

log = get_logger("health.service")
GROUP = "health"

DAILY_CHECKIN_LOCAL_TIME = (20, 0)  # 20:00 in AIA_TIMEZONE
WEEKLY_REPORT = (MONDAY, 8, 0)  # Monday 08:00


async def _send_daily_checkin() -> None:
    target = await principal_mod.principal_whatsapp()
    if not target:
        log.warning("daily_checkin_skipped_no_principal")
        return
    await workflow.daily_accountability(get_settings().tenant_id, target)


async def _send_weekly_report() -> None:
    target = await principal_mod.principal_whatsapp()
    if not target:
        log.warning("weekly_report_skipped_no_principal")
        return
    await workflow.weekly_checkin(get_settings().tenant_id, target)


async def _run() -> None:
    bus = get_bus()
    log.info("health_agent_starting")
    await asyncio.gather(
        bus.consume(f"{Streams.WHATSAPP_INBOUND}.health", GROUP, workflow.on_whatsapp),
        bus.consume(Streams.HEALTH_UPDATE, GROUP, workflow.on_health_update),
        run_daily("daily_checkin", *DAILY_CHECKIN_LOCAL_TIME, _send_daily_checkin),
        run_weekly("weekly_report", *WEEKLY_REPORT, _send_weekly_report),
    )


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
