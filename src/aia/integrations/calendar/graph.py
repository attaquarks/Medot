"""Microsoft Graph calendar adapter (stub conforming to CalendarProvider).

Implement against https://graph.microsoft.com/v1.0/me/events and /calendar/getSchedule
for free/busy. Structure mirrors google.py.
"""
from __future__ import annotations

from datetime import datetime

from .base import CalendarProvider, CalendarSlot


class GraphCalendarProvider(CalendarProvider):
    async def list_events(self, tenant_id: str, start: datetime, end: datetime) -> list[dict]:
        raise NotImplementedError("TODO(impl): GET /me/calendarView")

    async def free_slots(self, tenant_id, start, end, duration_min) -> list[CalendarSlot]:
        raise NotImplementedError("TODO(impl): POST /me/calendar/getSchedule")

    async def create_event(self, tenant_id, title, start, end, attendees) -> str:
        raise NotImplementedError("TODO(impl): POST /me/events")

    async def update_event(self, tenant_id, event_id, **changes) -> None:
        raise NotImplementedError("TODO(impl): PATCH /me/events/{id}")

    async def cancel_event(self, tenant_id, event_id) -> None:
        raise NotImplementedError("TODO(impl): DELETE /me/events/{id}")
