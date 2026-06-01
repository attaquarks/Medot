"""Business agent worker entrypoint:  python -m aia.agents.business.service

Subscribes to its event streams and runs forever. Each stream gets its own
consumer task; the event bus provides at-least-once delivery via consumer groups.
"""
from __future__ import annotations

import asyncio

from ...events.bus import Streams, get_bus
from ...logging import configure_logging, get_logger
from . import workflow

log = get_logger("business.service")
GROUP = "business"


async def _run() -> None:
    bus = get_bus()
    log.info("business_agent_starting")
    await asyncio.gather(
        # Per-agent inbound stream: the gateway routes each WhatsApp message to
        # exactly one agent so the two never both answer the same message.
        bus.consume(f"{Streams.WHATSAPP_INBOUND}.business", GROUP, workflow.on_whatsapp),
        bus.consume(Streams.EMAIL_RECEIVED, GROUP, workflow.on_email),
        bus.consume(Streams.PHONE_INBOUND, GROUP, workflow.on_phone),
        # calendar.changed handled inline by the gateway poller in this scaffold.
    )


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
