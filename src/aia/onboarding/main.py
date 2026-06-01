"""Onboarding wizard:  python -m aia.onboarding.main

Steps the user sees:
  1. Master key — generated automatically into the OS keychain on first load.
  2. Connect Google / Microsoft via OAuth (Email + Calendar in one consent).
  3. Pair WhatsApp — scan the QR rendered from the Baileys sidecar.
  4. Choose nutrition provider + set preferences.
  5. Launch — instructions to start both agents.

Security: tokens are exchanged server-side and stored encrypted (envelope cipher).
The browser never sees a token.
"""
from __future__ import annotations

import secrets
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from ..config import get_settings
from ..db.base import session_scope
from ..db.models import Credential
from ..integrations.oauth import OAuthManager
from ..logging import configure_logging, get_logger
from ..security.crypto import load_or_create_master_key

log = get_logger("onboarding")
app = FastAPI(title="AIA Onboarding")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_oauth = OAuthManager()
_states: dict[str, str] = {}  # state -> provider (CSRF protection)


async def _connected() -> dict[str, bool]:
    async with session_scope() as s:
        rows = (await s.execute(select(Credential.provider))).scalars().all()
    have = set(rows)
    return {"google": "google" in have, "microsoft": "microsoft" in have}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    load_or_create_master_key()  # ensure the keychain entry exists
    status = await _connected()
    wa_ok = False
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            wa_ok = (await http.get(f"{get_settings().whatsapp_gateway_url}/health")).json().get("connected", False)
    except Exception:
        pass
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "status": status, "wa_connected": wa_ok,
         "gateway": get_settings().whatsapp_gateway_url},
    )


@app.get("/connect/{provider}")
async def connect(provider: str) -> RedirectResponse:
    state = secrets.token_urlsafe(16)
    _states[state] = provider
    return RedirectResponse(_oauth.authorization_url(provider, state))


@app.get("/oauth/callback")
async def callback(code: str, state: str) -> RedirectResponse:
    provider = _states.pop(state, None)
    if not provider:
        return RedirectResponse("/?error=bad_state")
    await _oauth.exchange_code(provider, code, get_settings().tenant_id)
    log.info("provider_connected", provider=provider)
    return RedirectResponse("/?connected=" + provider)


@app.get("/whatsapp", response_class=HTMLResponse)
async def whatsapp(request: Request) -> HTMLResponse:
    """Render the QR served by the Baileys sidecar (data-URL PNG)."""
    qr = None
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            qr = (await http.get(f"{get_settings().whatsapp_gateway_url}/qr")).json().get("qr")
    except Exception as exc:
        log.warning("qr_fetch_failed", error=str(exc))
    return templates.TemplateResponse("index.html", {"request": request, "qr": qr,
                                                      "status": await _connected(),
                                                      "wa_connected": False,
                                                      "gateway": get_settings().whatsapp_gateway_url})


def main() -> None:
    configure_logging()
    uvicorn.run(app, host="0.0.0.0", port=get_settings().onboarding_port)


if __name__ == "__main__":
    main()
