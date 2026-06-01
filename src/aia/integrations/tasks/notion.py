"""Notion task provider (stub). Implement with the Notion API + NOTION_TOKEN,
creating pages in a user-selected database. Conforms to TaskProvider."""
from __future__ import annotations

from datetime import datetime

from .base import TaskProvider


class NotionTaskProvider(TaskProvider):
    async def add(self, tenant_id: str, title: str, due_at: datetime | None = None) -> str:
        raise NotImplementedError("TODO(impl): POST https://api.notion.com/v1/pages")

    async def list_open(self, tenant_id: str) -> list[dict]:
        raise NotImplementedError("TODO(impl): POST /v1/databases/{id}/query")

    async def complete(self, tenant_id: str, task_id: str) -> None:
        raise NotImplementedError("TODO(impl): PATCH /v1/pages/{id}")
