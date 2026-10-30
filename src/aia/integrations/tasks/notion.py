"""Notion task provider — pages in a Notion database (NOTION_TOKEN).

Expects a database (NOTION_DATABASE_ID) with the standard properties this
provider maps: Name (title), Done (checkbox), Due (date). All optional extras
are ignored, so any simple task database works.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from ...config import get_settings
from .base import TaskProvider

NOTION_VERSION = "2022-06-28"


class NotionTaskProvider(TaskProvider):
    def _client(self) -> httpx.AsyncClient:
        s = get_settings()
        return httpx.AsyncClient(
            timeout=30,
            base_url="https://api.notion.com/v1/",
            headers={
                "Authorization": f"Bearer {s.notion_token}",
                "Notion-Version": NOTION_VERSION,
            },
        )

    async def add(self, tenant_id: str, title: str, due_at: datetime | None = None) -> str:
        s = get_settings()
        if not s.notion_database_id:
            raise RuntimeError("NOTION_DATABASE_ID not configured.")
        properties: dict = {"Name": {"title": [{"text": {"content": title}}]}}
        if due_at:
            properties["Due"] = {"date": {"start": due_at.date().isoformat()}}
        async with self._client() as http:
            r = await http.post(
                "/pages", json={"parent": {"database_id": s.notion_database_id}, "properties": properties}
            )
            r.raise_for_status()
            return r.json()["id"]

    async def list_open(self, tenant_id: str) -> list[dict]:
        s = get_settings()
        if not s.notion_database_id:
            raise RuntimeError("NOTION_DATABASE_ID not configured.")
        body = {"filter": {"property": "Done", "checkbox": {"equals": False}}}
        async with self._client() as http:
            r = await http.post(f"/databases/{s.notion_database_id}/query", json=body)
            r.raise_for_status()
            results = r.json().get("results", [])
        rows: list[dict] = []
        for page in results:
            props = page.get("properties", {})
            title = "".join(
                t.get("plain_text", "") for t in props.get("Name", {}).get("title", [])
            )
            rows.append({"id": page["id"], "title": title, "status": "open"})
        return rows

    async def complete(self, tenant_id: str, task_id: str) -> None:
        async with self._client() as http:
            r = await http.patch(
                f"/pages/{task_id}", json={"properties": {"Done": {"checkbox": True}}}
            )
            r.raise_for_status()
