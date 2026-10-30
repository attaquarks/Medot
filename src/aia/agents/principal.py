"""Resolve the principal's (owner's) WhatsApp id for proactive/escalation messages.

Resolution order:
  1. tenant.preferences["principal_whatsapp"]  (set per-tenant; hosted-ready)
  2. AIA_PRINCIPAL_WHATSAPP env
  3. the first entry of WHATSAPP_ALLOWED_NUMBERS

Returns normalized digits (see gateway.router.normalize_peer) or None when
nothing is configured — callers must skip the send in that case.
"""
from __future__ import annotations

from sqlalchemy import select

from ..config import get_settings
from ..db.base import session_scope
from ..db.models import Tenant
from ..gateway.router import normalize_peer
from ..logging import get_logger

log = get_logger("principal")


async def principal_whatsapp(tenant_id: str | None = None) -> str | None:
    s = get_settings()
    tenant_id = tenant_id or s.tenant_id

    try:
        async with session_scope() as db:
            row = (
                await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
            ).scalars().first()
            if row:
                value = (row.preferences or {}).get("principal_whatsapp")
                if value:
                    return normalize_peer(str(value))
    except Exception as exc:  # DB unavailable: env fallback still works
        log.warning("principal_db_lookup_failed", error=str(exc))

    if s.principal_whatsapp:
        return normalize_peer(s.principal_whatsapp)

    first_allowed = s.whatsapp_allowed_numbers.split(",")[0].strip()
    if first_allowed:
        return normalize_peer(first_allowed)
    return None
