"""Health agent worker entrypoint:  python -m aia.agents.health.service"""
from __future__ import annotations

import asyncio

from ...events.bus import Streams, get_bus
from ...logging import configure_logging, get_logger
from . import workflow

log = get_logger("health.service")
GROUP = "health"


async def _run() -> None:
    bus = get_bus()
    log.info("health_agent_starting")
    await asyncio.gather(
        bus.consume(f"{Streams.WHATSAPP_INBOUND}.health", GROUP, workflow.on_whatsapp),
        bus.consume(Streams.HEALTH_UPDATE, GROUP, workflow.on_health_update),
    )


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
