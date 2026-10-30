"""Microsoft Graph calendar adapter (Outlook / Microsoft 365).

Mirrors google.py: REST + the stored, auto-refreshing Microsoft OAuth token.
`free_slots` pulls the calendar view and computes open windows locally.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from ..oauth import OAuthManager
from .base import CalendarProvider, CalendarSlot, gaps

API = "https://graph.microsoft.com/v1.0/me"


def _ms_datetime(dt: datetime) -> dict:
    """Graph wants {dateTime (naive), timeZone (IANA or Windows)}."""
    return {"dateTime": dt.replace(tzinfo=None).isoformat(), "timeZone": "UTC"}


class GraphCalendarProvider(CalendarProvider):
    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=30)

    async def _token(self, tenant_id: str) -> str:
        # Auto-refreshes via refresh_token when the stored token has expired.
        return await OAuthManager().get_access_token(tenant_id, "microsoft")

    async def list_events(self, tenant_id: str, start: datetime, end: datetime) -> list[dict]:
        tok = await self._token(tenant_id)
        async with self._client() as http:
            r = await http.get(
                f"{API}/calendarview",
                headers={"Authorization": f"Bearer {tok}", "Prefer": 'outlook.timezone="UTC"'},
                params={"startDateTime": start.isoformat(), "endDateTime": end.isoformat()},
            )
            r.raise_for_status()
            return [
                {
                    "id": e["id"],
                    "summary": e.get("subject", ""),
                    "start": e.get("start", {}).get("dateTime"),
                    "end": e.get("end", {}).get("dateTime"),
                    "attendees": [
                        a.get("emailAddress", {}).get("address", "") for a in e.get("attendees", [])
                    ],
                }
                for e in r.json().get("value", [])
            ]

    async def free_slots(
        self, tenant_id: str, start: datetime, end: datetime, duration_min: int
    ) -> list[CalendarSlot]:
        events = await self.list_events(tenant_id, start, end)
        busy = []
        for e in events:
            b_start = datetime.fromisoformat(str(e["start"]).replace("Z", "+00:00"))
            b_end = datetime.fromisoformat(str(e["end"]).replace("Z", "+00:00"))
            busy.append((b_start, b_end))
        return gaps(start, end, busy, duration_min)

    async def create_event(
        self, tenant_id: str, title: str, start: datetime, end: datetime, attendees: list[str]
    ) -> str:
        tok = await self._token(tenant_id)
        body = {
            "subject": title,
            "start": _ms_datetime(start),
            "end": _ms_datetime(end),
            "attendees": [{"emailAddress": {"address": a}} for a in attendees],
        }
        async with self._client() as http:
            r = await http.post(f"{API}/events", headers={"Authorization": f"Bearer {tok}"}, json=body)
            r.raise_for_status()
            return r.json()["id"]

    async def update_event(self, tenant_id: str, event_id: str, **changes) -> None:
        tok = await self._token(tenant_id)
        body: dict = {}
        if "start" in changes:
            body["start"] = _ms_datetime(changes["start"])
        if "end" in changes:
            body["end"] = _ms_datetime(changes["end"])
        if "title" in changes:
            body["subject"] = changes["title"]
        async with self._client() as http:
            r = await http.patch(
                f"{API}/events/{event_id}", headers={"Authorization": f"Bearer {tok}"}, json=body
            )
            r.raise_for_status()

    async def cancel_event(self, tenant_id: str, event_id: str) -> None:
        tok = await self._token(tenant_id)
        async with self._client() as http:
            r = await http.delete(f"{API}/events/{event_id}", headers={"Authorization": f"Bearer {tok}"})
            r.raise_for_status()
