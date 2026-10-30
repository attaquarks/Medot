from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class CalendarSlot:
    starts_at: datetime
    ends_at: datetime


class CalendarProvider(ABC):
    @abstractmethod
    async def list_events(self, tenant_id: str, start: datetime, end: datetime) -> list[dict]: ...

    @abstractmethod
    async def free_slots(
        self, tenant_id: str, start: datetime, end: datetime, duration_min: int
    ) -> list[CalendarSlot]: ...

    @abstractmethod
    async def create_event(
        self, tenant_id: str, title: str, start: datetime, end: datetime, attendees: list[str]
    ) -> str: ...

    @abstractmethod
    async def update_event(self, tenant_id: str, event_id: str, **changes) -> None: ...

    @abstractmethod
    async def cancel_event(self, tenant_id: str, event_id: str) -> None: ...


def gaps(
    start: datetime, end: datetime, busy: list[tuple[datetime, datetime]], duration_min: int
) -> list[CalendarSlot]:
    """Return open windows >= duration between busy intervals, sorted.

    Naive busy endpoints (as some providers return them) are treated as UTC.
    """
    need = timedelta(minutes=duration_min)

    def aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    intervals = sorted((aware(b_start), aware(b_end)) for b_start, b_end in busy)
    slots: list[CalendarSlot] = []
    cursor = start
    for b_start, b_end in intervals:
        if b_end <= cursor:
            continue  # busy block ended before the window or already passed
        if b_start >= end:
            break
        if b_start - cursor >= need:
            slots.append(CalendarSlot(cursor, b_start))
        cursor = max(cursor, b_end)
    if end - cursor >= need:
        slots.append(CalendarSlot(cursor, end))
    return slots


def get_calendar_provider(provider: str = "google") -> CalendarProvider:
    if provider in ("outlook", "microsoft", "m365"):
        from .graph import GraphCalendarProvider

        return GraphCalendarProvider()
    from .google import GoogleCalendarProvider

    return GoogleCalendarProvider()
