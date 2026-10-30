"""Inbound WhatsApp safety: peer allowlist, principal resolution, tz parsing."""
from datetime import datetime

import pytest


# --------------------------- allowlist ----------------------------------------
def test_is_allowed_accepts_various_jid_shapes():
    from aia.gateway.router import is_allowed, normalize_peer

    assert normalize_peer("15551234567@s.whatsapp.net") == "15551234567"
    assert normalize_peer("15551234567@c.us") == "15551234567"
    assert normalize_peer("+1 (555) 123-4567") == "15551234567"
    assert is_allowed("15551234567@s.whatsapp.net", "15551234567")
    assert is_allowed("15551234567", " 15551234567 , 15559999999 ")


def test_is_allowed_blocks_unknown_number():
    from aia.gateway.router import is_allowed

    assert not is_allowed("19999999999@s.whatsapp.net", "15551234567")


def test_is_allowed_open_when_no_allowlist_configured():
    from aia.gateway.router import is_allowed

    assert is_allowed("anyone@s.whatsapp.net", "")
    assert is_allowed("anyone", "  ")


# --------------------------- principal ----------------------------------------
@pytest.mark.usefixtures("db_env")
async def test_principal_prefers_tenant_preference():
    from aia.agents.principal import principal_whatsapp
    from aia.db.base import session_scope
    from aia.db.models import Tenant

    async with session_scope() as s:
        s.add(Tenant(tenant_id="t1", preferences={"principal_whatsapp": "15551112222"}))

    assert await principal_whatsapp("t1") == "15551112222"


async def test_principal_falls_back_to_env_then_first_allowed(monkeypatch):
    from aia.agents.principal import principal_whatsapp
    from aia.config import get_settings

    monkeypatch.setenv("AIA_PRINCIPAL_WHATSAPP", "15553334444")
    monkeypatch.setenv("AIA_TENANT_ID", "t-env")
    get_settings.cache_clear()
    try:
        assert await principal_whatsapp() == "15553334444"
    finally:
        get_settings.cache_clear()

    monkeypatch.delenv("AIA_PRINCIPAL_WHATSAPP")
    monkeypatch.setenv("WHATSAPP_ALLOWED_NUMBERS", "15557778888, 15551110000")
    get_settings.cache_clear()
    try:
        assert await principal_whatsapp() == "15557778888"
    finally:
        get_settings.cache_clear()


# --------------------------- tz-aware parsing ----------------------------------
def test_tool_datetime_attaches_configured_timezone(monkeypatch):
    from aia.config import get_settings
    from aia.agents.business.tools import _dt

    monkeypatch.setenv("AIA_TIMEZONE", "Asia/Karachi")
    get_settings.cache_clear()
    try:
        dt = _dt("2026-10-28T14:00:00")
        assert dt.utcoffset() is not None
        assert dt.isoformat().endswith("+05:00")
        # Already-aware input passes through untouched.
        aware = datetime.fromisoformat("2026-10-28T14:00:00+02:00")
        assert _dt("2026-10-28T14:00:00+02:00") == aware
    finally:
        get_settings.cache_clear()
