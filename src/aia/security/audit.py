"""Append-only audit logging.

Every security- or privacy-sensitive action (credential read, email sent, call
placed, calendar mutation, escalation) is recorded to the `audit_logs` table so a
user can answer "what did my agent do, and when?". This is a thin helper; the
table is defined in `aia.db.models`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..logging import get_logger

log = get_logger("audit")


async def audit(
    session: AsyncSession,
    *,
    tenant_id: str,
    agent: str,
    action: str,
    resource: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write an audit row. Import the model lazily to avoid a cycle."""
    from ..db.models import AuditLog

    row = AuditLog(
        tenant_id=tenant_id,
        agent=agent,
        action=action,
        resource=resource,
        meta=metadata or {},
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    # Caller owns the transaction/commit.
    log.info("audit", agent=agent, action=action, resource=resource)
