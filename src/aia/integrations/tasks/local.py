"""Local task provider — uses the business.tasks table. Zero external setup,
the default so the system is fully functional offline."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from ...db.base import session_scope
from ...db.models import Task
from .base import TaskProvider


class LocalTaskProvider(TaskProvider):
    async def add(self, tenant_id: str, title: str, due_at: datetime | None = None) -> str:
        async with session_scope() as s:
            t = Task(tenant_id=tenant_id, title=title, due_at=due_at, source="agent")
            s.add(t)
            await s.flush()
            return t.id

    async def list_open(self, tenant_id: str) -> list[dict]:
        async with session_scope() as s:
            rows = (await s.execute(
                select(Task).where(Task.tenant_id == tenant_id, Task.status != "done")
                .order_by(Task.due_at.is_(None), Task.due_at)
            )).scalars().all()
            return [{"id": t.id, "title": t.title, "status": t.status, "due_at": t.due_at} for t in rows]

    async def complete(self, tenant_id: str, task_id: str) -> None:
        async with session_scope() as s:
            t = await s.get(Task, task_id)
            if t and t.tenant_id == tenant_id:
                t.status = "done"
