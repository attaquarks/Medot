"""Google Calendar adapter (REST + stored OAuth token).

`free_slots` is the workhorse for the reschedule flow: it pulls busy intervals
via freeBusy and returns open windows of the requested duration.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from ..oauth import OAuthManager
from .base import CalendarProvider, CalendarSlot

API = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarProvider(CalendarProvider):
    async def _token(self, tenant_id: str) -> str:
        tok = await OAuthManager.load_token(tenant_id, "google")
        if not tok:
            raise RuntimeError("Google account not connected — run onboarding.")
        return tok["access_token"]

    async def list_events(self, tenant_id: str, start: datetime, end: datetime) -> list[dict]:
        tok = await self._token(tenant_id)
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.get(
                f"{API}/calendars/primary/events",
                headers={"Authorization": f"Bearer {tok}"},
                params={
                    "timeMin": start.isoformat(), "timeMax": end.isoformat(),
                    "singleEvents": "true", "orderBy": "startTime",
                },
            )
            r.raise_for_status()
            return r.json().get("items", [])

    async def free_slots(
        self, tenant_id: str, start: datetime, end: datetime, duration_min: int
    ) -> list[CalendarSlot]:
        tok = await self._token(tenant_id)
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(
                f"{API}/freeBusy",
                headers={"Authorization": f"Bearer {tok}"},
                json={"timeMin": start.isoformat(), "timeMax": end.isoformat(),
                      "items": [{"id": "primary"}]},
            )
            r.raise_for_status()
            busy = r.json()["calendars"]["primary"]["busy"]
        return _gaps(start, end, busy, duration_min)

    async def create_event(
        self, tenant_id: str, title: str, start: datetime, end: datetime, attendees: list[str]
    ) -> str:
        tok = await self._token(tenant_id)
        body = {
            "summary": title,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
            "attendees": [{"email": a} for a in attendees],
        }
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(
                f"{API}/calendars/primary/events?sendUpdates=all",
                headers={"Authorization": f"Bearer {tok}"}, json=body,
            )
            r.raise_for_status()
            return r.json()["id"]

    async def update_event(self, tenant_id: str, event_id: str, **changes) -> None:
        tok = await self._token(tenant_id)
        body: dict = {}
        if "start" in changes:
            body["start"] = {"dateTime": changes["start"].isoformat()}
        if "end" in changes:
            body["end"] = {"dateTime": changes["end"].isoformat()}
        if "title" in changes:
            body["summary"] = changes["title"]
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.patch(
                f"{API}/calendars/primary/events/{event_id}?sendUpdates=all",
                headers={"Authorization": f"Bearer {tok}"}, json=body,
            )
            r.raise_for_status()

    async def cancel_event(self, tenant_id: str, event_id: str) -> None:
        tok = await self._token(tenant_id)
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.delete(
                f"{API}/calendars/primary/events/{event_id}?sendUpdates=all",
                headers={"Authorization": f"Bearer {tok}"},
            )
            r.raise_for_status()


def _gaps(start: datetime, end: datetime, busy: list[dict], duration_min: int) -> list[CalendarSlot]:
    """Return open windows >= duration between busy intervals (naive, hour-aligned)."""
    need = timedelta(minutes=duration_min)
    intervals = sorted(
        (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])) for b in busy
    )
    slots: list[CalendarSlot] = []
    cursor = start
    for b_start, b_end in intervals:
        if b_start - cursor >= need:
            slots.append(CalendarSlot(cursor, b_start))
        cursor = max(cursor, b_end)
    if end - cursor >= need:
        slots.append(CalendarSlot(cursor, end))
    return slots
