"""Tiny asyncio scheduler for proactive agent messages.

No new dependency: each job is a coroutine loop that sleeps until its next
local-time occurrence and then fires. Failures are logged and the loop
continues — a missed notification must never kill the agent worker.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..config import get_settings
from ..logging import get_logger

log = get_logger("scheduler")

MONDAY = 0  # weekday numbering per datetime.weekday()


def _now(tz_name: str | None = None) -> datetime:
    return datetime.now(ZoneInfo(tz_name or get_settings().timezone))


def seconds_until(hour: int, minute: int, now: datetime | None = None) -> float:
    """Seconds until the next occurrence of a local time (>= 1s in the future)."""
    now = now or _now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo(get_settings().timezone))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def seconds_until_weekday(weekday: int, hour: int, minute: int, now: datetime | None = None) -> float:
    """Seconds until the next given weekday at a local time (today counts)."""
    now = now or _now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo(get_settings().timezone))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (weekday - target.weekday()) % 7
    if days_ahead == 0 and target <= now:
        days_ahead = 7
    target += timedelta(days=days_ahead)
    return (target - now).total_seconds()


async def run_daily(job: str, hour: int, minute: int, fn) -> None:
    """Fire `fn` every day at the configured local time, forever."""
    while True:
        delay = seconds_until(hour, minute)
        log.info("scheduled_next", job=job, in_seconds=round(delay))
        await asyncio.sleep(delay)
        try:
            await fn()
            log.info("scheduled_job_done", job=job)
        except Exception as exc:
            log.error("scheduled_job_failed", job=job, error=str(exc))


async def run_weekly(job: str, weekday: int, hour: int, minute: int, fn) -> None:
    """Fire `fn` every week on `weekday` at the configured local time, forever."""
    while True:
        delay = seconds_until_weekday(weekday, hour, minute)
        log.info("scheduled_next", job=job, in_seconds=round(delay))
        await asyncio.sleep(delay)
        try:
            await fn()
            log.info("scheduled_job_done", job=job)
        except Exception as exc:
            log.error("scheduled_job_failed", job=job, error=str(exc))
