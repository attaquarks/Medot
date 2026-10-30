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
from fastapi import FastAPI, Request, Form
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


async def _connected() -> dict[str, list[str]]:
    async with session_scope() as s:
        rows = (await s.execute(select(Credential.provider, Credential.account_label))).all()
    res = {"google": [], "microsoft": []}
    for provider, label in rows:
        if provider in res and label:
            res[provider].append(label)
    return res


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
    settings = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request, 
            "status": status, 
            "wa_connected": wa_ok,
            "gateway": settings.whatsapp_gateway_url,
            "settings": settings
        },
    )

@app.post("/configure")
async def configure(
    request: Request,
    enabled_agents: str = Form("business,health"),
    llm_provider: str = Form("local"),
    openai_api_key: str = Form(""),
    anthropic_api_key: str = Form(""),
    whatsapp_allowed_numbers: str = Form("")
) -> RedirectResponse:
    import dotenv
    env_path = Path("/app/.env") if Path("/app/.env").exists() else Path(".env")
    
    dotenv.set_key(env_path, "ENABLED_AGENTS", enabled_agents)
    dotenv.set_key(env_path, "WHATSAPP_ALLOWED_NUMBERS", whatsapp_allowed_numbers)
    
    if llm_provider == "openai":
        dotenv.set_key(env_path, "LLM_FORCE_CLOUD", "1")
        dotenv.set_key(env_path, "OPENAI_API_KEY", openai_api_key)
    elif llm_provider == "anthropic":
        dotenv.set_key(env_path, "LLM_FORCE_CLOUD", "1")
        dotenv.set_key(env_path, "ANTHROPIC_API_KEY", anthropic_api_key)
    else:
        dotenv.set_key(env_path, "LLM_FORCE_CLOUD", "0")
        
    return RedirectResponse("/?saved=1", status_code=303)


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
    settings = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="index.html", 
        context={
            "request": request, 
            "qr": qr,
            "status": await _connected(),
            "wa_connected": False,
            "gateway": settings.whatsapp_gateway_url,
            "settings": settings
        }
    )


def main() -> None:
    configure_logging()
    uvicorn.run(app, host="0.0.0.0", port=get_settings().onboarding_port)


if __name__ == "__main__":
    main()
