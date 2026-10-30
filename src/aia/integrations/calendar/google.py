"""Google Calendar adapter (REST + stored OAuth token).

`free_slots` is the workhorse for the reschedule flow: it pulls busy intervals
via freeBusy and returns open windows of the requested duration.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from ..oauth import OAuthManager
from .base import CalendarProvider, CalendarSlot, gaps

API = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarProvider(CalendarProvider):
    async def _token(self, tenant_id: str) -> str:
        # Auto-refreshes via refresh_token when the stored token has expired.
        return await OAuthManager().get_access_token(tenant_id, "google")

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
        return gaps(
            start, end,
            [(datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])) for b in busy],
            duration_min,
        )

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
