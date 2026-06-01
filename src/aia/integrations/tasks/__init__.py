"""Task-manager abstraction (local DB default; Notion / Todoist / Google Tasks)."""
from .base import TaskProvider, get_task_provider

__all__ = ["TaskProvider", "get_task_provider"]
