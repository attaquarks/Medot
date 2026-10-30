"""Todoist task provider — Todoist REST API v2 + TODOIST_TOKEN."""
from __future__ import annotations

from datetime import datetime

import httpx

from ...config import get_settings
from .base import TaskProvider


class TodoistTaskProvider(TaskProvider):
    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=30,
            base_url="https://api.todoist.com/rest/v2/",
            headers={"Authorization": f"Bearer {get_settings().todoist_token}"},
        )

    async def add(self, tenant_id: str, title: str, due_at: datetime | None = None) -> str:
        body: dict = {"content": title}
        if due_at:
            body["due_datetime"] = due_at.isoformat()
        async with self._client() as http:
            r = await http.post("/tasks", json=body)
            r.raise_for_status()
            return r.json()["id"]

    async def list_open(self, tenant_id: str) -> list[dict]:
        # GET /tasks returns only active (non-closed) tasks.
        async with self._client() as http:
            r = await http.get("/tasks")
            r.raise_for_status()
            tasks = r.json()
        return [{"id": t["id"], "title": t["content"], "status": "open"} for t in tasks]

    async def complete(self, tenant_id: str, task_id: str) -> None:
        async with self._client() as http:
            r = await http.post(f"/tasks/{task_id}/close")
            r.raise_for_status()
