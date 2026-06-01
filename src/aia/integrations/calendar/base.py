from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


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


def get_calendar_provider(provider: str = "google") -> CalendarProvider:
    if provider in ("outlook", "microsoft", "m365"):
        from .graph import GraphCalendarProvider

        return GraphCalendarProvider()
    from .google import GoogleCalendarProvider

    return GoogleCalendarProvider()
