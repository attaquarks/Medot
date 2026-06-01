"""Todoist task provider (stub). Implement with the Todoist REST API v2 +
TODOIST_TOKEN. Conforms to TaskProvider."""
from __future__ import annotations

from datetime import datetime

from .base import TaskProvider


class TodoistTaskProvider(TaskProvider):
    async def add(self, tenant_id: str, title: str, due_at: datetime | None = None) -> str:
        raise NotImplementedError("TODO(impl): POST https://api.todoist.com/rest/v2/tasks")

    async def list_open(self, tenant_id: str) -> list[dict]:
        raise NotImplementedError("TODO(impl): GET /rest/v2/tasks")

    async def complete(self, tenant_id: str, task_id: str) -> None:
        raise NotImplementedError("TODO(impl): POST /rest/v2/tasks/{id}/close")
