"""Loopback service API for the Medot desktop console.

Binds to 127.0.0.1 only. Every request (except /health) must carry the
per-launch token the runtime printed to stdout at startup — this keeps other
local processes from driving the desktop's session.
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .. import __version__
from ..config import get_settings
from ..localstore import keystore as keystore_mod
from ..localstore import paths
from ..supabase import auth as supabase_auth
from ..supabase import bootstrap as supabase_bootstrap

app = FastAPI(title="Medot Runtime", version=__version__)

_launch_token: str | None = None


def set_launch_token(token: str) -> None:
    global _launch_token
    _launch_token = token


def generate_launch_token() -> str:
    return uuid.uuid4().hex


def require_token(x_launch_token: str = Header(default="")) -> None:
    if not _launch_token or x_launch_token != _launch_token:
        raise HTTPException(status_code=401, detail="invalid launch token")


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {"ok": True, "version": __version__, "supabase_configured": settings.configured}


class CallbackBody(BaseModel):
    callback_url: str


@app.post("/auth/start")
async def auth_start(_: None = Depends(require_token)) -> dict:
    start = supabase_auth.start_google_signin(open_browser=True)
    return {"authorize_url": start.authorize_url}


@app.post("/auth/callback")
async def auth_callback(body: CallbackBody, _: None = Depends(require_token)) -> dict:
    try:
        session = supabase_auth.complete_signin(body.callback_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # exchange failures surface verbatim to the console
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    user_id = session["user"]["id"]
    supabase_auth.remember_user(user_id)
    return {"user_id": user_id}


@app.get("/session")
async def session(_: None = Depends(require_token)) -> dict:
    restored = supabase_auth.load_session()
    if not restored:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user_id": restored.get("user", {}).get("id"),
        "expires_at": restored.get("expires_at"),
    }


@app.get("/bootstrap")
async def bootstrap(_: None = Depends(require_token)) -> dict:
    restored = supabase_auth.load_session()
    if not restored:
        raise HTTPException(status_code=401, detail="not signed in")
    user_id = restored["user"]["id"]
    from ..supabase.client import client_for_session

    init = await asyncio.to_thread(
        supabase_bootstrap.verify_initialization,
        client_for_session(restored["access_token"]),
        user_id,
    )
    return {
        "complete": init.complete,
        "missing": init.missing,
        "me_identity_id": init.me_identity_id,
        "global_domain_id": init.global_domain_id,
    }


@app.post("/session/signout")
async def signout(_: None = Depends(require_token)) -> dict:
    restored = supabase_auth.load_session()
    if restored:
        keystore = keystore_mod.get_keystore()
        keystore.delete_secret(supabase_auth.session_account(restored["user"]["id"]))
        keystore.delete_secret("supabase.last_user")
    return {"ok": True}


# --------------------------- WhatsApp connection -----------------------------

class ConnectBody(BaseModel):
    api_key: str


def _user_client() -> tuple[str, object]:
    """(user_id, Supabase client running as the user) or 401."""
    restored = supabase_auth.load_session()
    if not restored:
        raise HTTPException(status_code=401, detail="not signed in")
    user_id = restored["user"]["id"]
    from ..supabase.client import client_for_session

    return user_id, client_for_session(restored["access_token"])


@app.post("/whatsapp/connect")
async def whatsapp_connect(body: ConnectBody, _: None = Depends(require_token)) -> dict:
    """Store the pasted Agent Platform API key (keystore) and record the link."""
    from ..whatsapp import connection as wa

    user_id, client = await asyncio.to_thread(_user_client)
    try:
        result = await asyncio.to_thread(wa.connect, client, user_id, body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.as_dict()


@app.get("/whatsapp/status")
async def whatsapp_status(_: None = Depends(require_token)) -> dict:
    from ..whatsapp import connection as wa

    user_id, client = await asyncio.to_thread(_user_client)
    return (await asyncio.to_thread(wa.status, client, user_id)).as_dict()


@app.post("/whatsapp/disconnect")
async def whatsapp_disconnect(_: None = Depends(require_token)) -> dict:
    from ..whatsapp import connection as wa

    user_id, client = await asyncio.to_thread(_user_client)
    await asyncio.to_thread(wa.disconnect, client, user_id)
    return {"ok": True}


@app.get("/paths")
async def layout() -> dict:
    dirs = paths.ensure_layout()
    return {name: str(path) for name, path in dirs.items()}
