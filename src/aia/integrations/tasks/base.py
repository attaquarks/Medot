from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ...config import get_settings


class TaskProvider(ABC):
    @abstractmethod
    async def add(self, tenant_id: str, title: str, due_at: datetime | None = None) -> str: ...

    @abstractmethod
    async def list_open(self, tenant_id: str) -> list[dict]: ...

    @abstractmethod
    async def complete(self, tenant_id: str, task_id: str) -> None: ...


def get_task_provider(provider: str | None = None) -> TaskProvider:
    provider = provider or get_settings().tasks_provider
    if provider == "notion":
        from .notion import NotionTaskProvider

        return NotionTaskProvider()
    if provider == "todoist":
        from .todoist import TodoistTaskProvider

        return TodoistTaskProvider()
    from .local import LocalTaskProvider

    return LocalTaskProvider()
