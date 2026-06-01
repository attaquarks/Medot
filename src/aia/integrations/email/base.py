from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class EmailMessage:
    external_id: str
    sender: str
    subject: str
    snippet: str
    received_at: datetime | None = None


class EmailProvider(ABC):
    """Read / draft / send. Categorisation & urgency are done by the agent's LLM."""

    @abstractmethod
    async def list_recent(self, tenant_id: str, *, max_results: int = 20) -> list[EmailMessage]: ...

    @abstractmethod
    async def get_body(self, tenant_id: str, external_id: str) -> str: ...

    @abstractmethod
    async def send(self, tenant_id: str, to: str, subject: str, body: str) -> str: ...

    @abstractmethod
    async def create_draft(self, tenant_id: str, to: str, subject: str, body: str) -> str: ...


def get_email_provider(provider: str = "gmail") -> EmailProvider:
    if provider in ("outlook", "microsoft", "m365"):
        from .graph import GraphEmailProvider

        return GraphEmailProvider()
    from .gmail import GmailProvider

    return GmailProvider()
