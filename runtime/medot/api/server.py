"""Loopback service API for the Medot desktop console.

Binds to 127.0.0.1 only. Every request (except /health) must carry the
per-launch token the runtime printed to stdout at startup — this keeps other
local processes from driving the desktop's session.
"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .. import __version__
from ..config import get_settings
from ..localstore import keystore as keystore_mod
from ..localstore import paths
from ..supabase import auth as supabase_auth
from ..supabase import bootstrap as supabase_bootstrap
from ..whatsapp import manager as wa_manager
from ..whatsapp.baileys import BridgeError, BridgeSettings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Resume WhatsApp transports for the last signed-in user, if any."""
    restored = supabase_auth.load_session()
    if restored:
        try:
            user_id = restored["user"]["id"]
            from ..supabase.client import client_for_session

            client = client_for_session(restored["access_token"])
            await wa_manager.get_manager().resume(client, user_id)
        except Exception:  # noqa: BLE001, S110 - startup resume is best effort
            pass
    yield
    await wa_manager.shutdown_manager()


app = FastAPI(title="Medot Runtime", version=__version__, lifespan=lifespan)

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
# Two routes (docs/medot/03, decision 2026-11-02): the official Agent Platform
# and the unofficial Baileys bridge. Either, or both, can be connected.

def _user_client() -> tuple[str, object]:
    """(user_id, Supabase client running as the user) or 401."""
    restored = supabase_auth.load_session()
    if not restored:
        raise HTTPException(status_code=401, detail="not signed in")
    user_id = restored["user"]["id"]
    from ..supabase.client import client_for_session

    return user_id, client_for_session(restored["access_token"])


class AgentPlatformConnectBody(BaseModel):
    api_key: str


@app.post("/whatsapp/agent-platform/connect")
async def whatsapp_agent_platform_connect(body: AgentPlatformConnectBody, _: None = Depends(require_token)) -> dict:
    """Store the pasted Agent Platform API key (keystore) and start polling."""
    user_id, client = await asyncio.to_thread(_user_client)
    try:
        return await wa_manager.get_manager().connect_agent_platform(client, user_id, body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/whatsapp/agent-platform/disconnect")
async def whatsapp_agent_platform_disconnect(_: None = Depends(require_token)) -> dict:
    user_id, client = await asyncio.to_thread(_user_client)
    await wa_manager.get_manager().disconnect_agent_platform(client, user_id)
    return {"ok": True}


class BaileysConnectBody(BaseModel):
    mode: str = "self"
    allowed_users: list[str] = Field(default_factory=list)
    allow_all: bool = False
    group_policy: str = "pairing"
    group_allow: list[str] = Field(default_factory=list)
    require_mention: bool = False


@app.post("/whatsapp/baileys/connect")
async def whatsapp_baileys_connect(body: BaileysConnectBody, _: None = Depends(require_token)) -> dict:
    """Record the Baileys link + policy and spawn the bridge.

    Pairing is asynchronous: poll `GET /whatsapp/baileys/qr` until `paired`.
    """
    user_id, client = await asyncio.to_thread(_user_client)
    settings = BridgeSettings(
        mode=body.mode,
        allowed_users=body.allowed_users,
        allow_all=body.allow_all,
        group_policy=body.group_policy,
        group_allow=body.group_allow,
        require_mention=body.require_mention,
    )
    try:
        return await wa_manager.get_manager().connect_baileys(client, user_id, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BridgeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/whatsapp/baileys/qr")
async def whatsapp_baileys_qr(_: None = Depends(require_token)) -> dict:
    try:
        return await wa_manager.get_manager().baileys_qr()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BridgeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/whatsapp/baileys/disconnect")
async def whatsapp_baileys_disconnect(_: None = Depends(require_token)) -> dict:
    """Stop the bridge; the paired session is kept for next time."""
    user_id, client = await asyncio.to_thread(_user_client)
    await wa_manager.get_manager().disconnect_baileys(client, user_id)
    return {"ok": True}


@app.post("/whatsapp/baileys/logout")
async def whatsapp_baileys_logout(_: None = Depends(require_token)) -> dict:
    """Unpair entirely: the WhatsApp session is wiped, a new QR is required."""
    user_id, client = await asyncio.to_thread(_user_client)
    await wa_manager.get_manager().baileys_logout(client, user_id)
    return {"ok": True}


@app.get("/whatsapp/status")
async def whatsapp_status(_: None = Depends(require_token)) -> dict:
    return wa_manager.get_manager().status()


class SendBody(BaseModel):
    text: str
    transport: str | None = None  # agent_platform | baileys (default: first connected)
    to: str | None = None  # default: last inbound peer (the creator / self-chat)


@app.post("/whatsapp/send")
async def whatsapp_send(body: SendBody, _: None = Depends(require_token)) -> dict:
    try:
        return await wa_manager.get_manager().send(body.text, transport_name=body.transport, to=body.to)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc



# --------------------------- AI providers (BYOK) -----------------------------

class DiscoverBody(BaseModel):
    provider: str
    base_url: str | None = None
    api_key: str


@app.post("/providers/discover")
async def providers_discover(body: DiscoverBody, _: None = Depends(require_token)) -> dict:
    """Fetch the live model list from the provider (the key is not stored yet)."""
    from ..providers.discovery import discover_models

    try:
        return {"models": await discover_models(body.provider, body.base_url, body.api_key)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ProfileBody(BaseModel):
    name: str
    purpose: str = "chat"
    provider: str
    model: str
    api_base: str | None = None
    api_key: str | None = None


@app.get("/providers/profiles")
async def providers_list(_: None = Depends(require_token)) -> dict:
    from ..providers import profiles as profiles_mod

    user_id, client = await asyncio.to_thread(_user_client)
    rows = await asyncio.to_thread(profiles_mod.list_profiles, client, user_id)
    return {"profiles": rows}


@app.post("/providers/profiles")
async def providers_save(body: ProfileBody, _: None = Depends(require_token)) -> dict:
    from ..providers import profiles as profiles_mod

    user_id, client = await asyncio.to_thread(_user_client)
    try:
        saved = await asyncio.to_thread(
            profiles_mod.save_profile,
            client,
            user_id,
            keystore_mod.get_keystore(),
            profile_id=None,
            name=body.name,
            purpose=body.purpose,
            provider=body.provider,
            model=body.model,
            api_base=body.api_base,
            api_key=body.api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return saved


@app.delete("/providers/profiles/{profile_id}")
async def providers_delete(profile_id: str, _: None = Depends(require_token)) -> dict:
    from ..providers import profiles as profiles_mod

    user_id, client = await asyncio.to_thread(_user_client)
    try:
        await asyncio.to_thread(
            profiles_mod.delete_profile, client, user_id, keystore_mod.get_keystore(), profile_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/providers/profiles/{profile_id}/verify")
async def providers_verify(profile_id: str, _: None = Depends(require_token)) -> dict:
    """Real end-to-end check: call the model with the stored key right now."""
    from ..providers import profiles as profiles_mod

    user_id, client = await asyncio.to_thread(_user_client)
    try:
        return await profiles_mod.verify_profile(client, user_id, keystore_mod.get_keystore(), profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --------------------------- Identity registry (M2b) -------------------------

class IdentityCreateBody(BaseModel):
    name: str
    instructions_md: str
    description: str = ""
    icon: str | None = None
    model_profile_id: str | None = None


class IdentityUpdateBody(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    status: str | None = None
    model_profile_id: str | None = None


class IdentityInstructionsBody(BaseModel):
    content_md: str


@app.get("/identities")
async def identities_list(_: None = Depends(require_token)) -> dict:
    from ..identities import registry as identities_mod

    user_id, client = await asyncio.to_thread(_user_client)
    rows = await asyncio.to_thread(identities_mod.list_identities, client, user_id)
    return {"identities": rows}


@app.post("/identities")
async def identities_create(body: IdentityCreateBody, _: None = Depends(require_token)) -> dict:
    from ..identities import registry as identities_mod

    user_id, client = await asyncio.to_thread(_user_client)
    try:
        return await asyncio.to_thread(
            identities_mod.create_identity,
            client,
            user_id,
            name=body.name,
            instructions_md=body.instructions_md,
            description=body.description,
            icon=body.icon,
            model_profile_id=body.model_profile_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/identities/{identity_id}")
async def identities_update(identity_id: str, body: IdentityUpdateBody, _: None = Depends(require_token)) -> dict:
    from ..identities import registry as identities_mod

    user_id, client = await asyncio.to_thread(_user_client)
    try:
        updated = await asyncio.to_thread(
            identities_mod.update_identity,
            client,
            user_id,
            identity_id,
            name=body.name,
            description=body.description,
            icon=body.icon,
            status=body.status,
            model_profile_id=body.model_profile_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="no such identity")
    return updated


@app.put("/identities/{identity_id}/instructions")
async def identities_save_instructions(
    identity_id: str, body: IdentityInstructionsBody, _: None = Depends(require_token)
) -> dict:
    """Saving instructions creates a new active version; the old one is kept."""
    from ..identities import registry as identities_mod

    user_id, client = await asyncio.to_thread(_user_client)
    try:
        return await asyncio.to_thread(
            identities_mod.save_instructions, client, user_id, identity_id, body.content_md
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

# --------------------------- Approvals + activity (console) ------------------

class ApprovalDecisionBody(BaseModel):
    approved: bool


@app.get("/approvals")
async def approvals_list(_: None = Depends(require_token)) -> dict:
    """Pending approvals, then the recently decided ones (console Activity)."""
    user_id, client = await asyncio.to_thread(_user_client)

    def _load() -> dict:
        pending = (
            client.table("approvals")
            .select("id,action,summary,status,channel,created_at,decided_at")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .order("id", desc=True)
            .execute()
            .data
            or []
        )
        recent = (
            client.table("approvals")
            .select("id,action,summary,status,channel,created_at,decided_at")
            .eq("user_id", user_id)
            .in_("status", ["approved", "denied", "expired"])
            .order("id", desc=True)
            .limit(20)
            .execute()
            .data
            or []
        )
        return {"pending": pending, "recent": recent}

    return await asyncio.to_thread(_load)


@app.post("/approvals/{approval_id}/decide")
async def approvals_decide(
    approval_id: str, body: ApprovalDecisionBody, _: None = Depends(require_token)
) -> dict:
    """The console's Approve/Deny: resumes the interrupted run, like a
    WhatsApp YES/NO would."""
    from ..engine import wiring as engine_wiring

    user_id, client = await asyncio.to_thread(_user_client)

    def _row() -> dict | None:
        rows = (
            client.table("approvals")
            .select("id,run_id,identity_id,action,summary,payload,status")
            .eq("id", approval_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None

    pending = await asyncio.to_thread(_row)
    if not pending:
        raise HTTPException(status_code=404, detail="no such approval")
    if pending["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"already {pending['status']}")
    peer = (pending.get("payload") or {}).get("peer", "desktop")
    try:
        reply = await engine_wiring.apply_approval_decision(
            client, user_id, pending, body.approved, transport="desktop", peer=peer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "reply": reply}


@app.get("/activity")
async def activity_list(_: None = Depends(require_token)) -> dict:
    user_id, client = await asyncio.to_thread(_user_client)

    def _load() -> dict:
        rows = (
            client.table("activity_events")
            .select("id,event,detail,created_at,identity_id")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
            .data
            or []
        )
        return {"events": rows}

    return await asyncio.to_thread(_load)


# --------------------------- Engine (Me. thinking) ---------------------------

class TestTurnBody(BaseModel):
    text: str


@app.post("/engine/test-turn")
async def engine_test_turn(body: TestTurnBody, _: None = Depends(require_token)) -> dict:
    """Talk to Me. from the desktop: the full real flow (turn, tools,
    approvals) against the desktop conversation (peer "desktop"). If an
    approval is pending for that conversation, this message is the decision."""
    from ..engine import wiring as engine_wiring

    user_id, client = await asyncio.to_thread(_user_client)
    try:
        # persist the user's message first, exactly like the WhatsApp path does
        await asyncio.to_thread(
            wa_manager.persist_message,
            client,
            user_id,
            wa_manager.Envelope(
                transport="desktop", message_id="", peer="desktop", chat="desktop",
                sender="desktop", text=body.text,
            ),
        )
        await engine_wiring._run_inbound_flow(client, user_id, "desktop", "desktop", body.text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    rows = await asyncio.to_thread(engine_wiring.load_history, client, user_id, "desktop")
    reply = next((m.content for m in reversed(rows) if m.type == "ai"), "")
    return {"reply": reply}


@app.get("/paths")
async def layout() -> dict:
    dirs = paths.ensure_layout()
    return {name: str(path) for name, path in dirs.items()}
