"""Inbound gateway (FastAPI):  python -m aia.gateway.main

Endpoints:
  GET  /health                      liveness + WhatsApp transport status
  GET  /models                      models visible to the configured Ollama server
  POST /test/message                drive one agent turn over HTTP (local env only)
  POST /webhook/whatsapp            inbound from the Baileys Node sidecar
  GET  /webhook/whatsapp/cloud      Meta Cloud API verification handshake
  POST /webhook/whatsapp/cloud      inbound from Meta Cloud API
  POST /webhook/twilio/voice        returns TwiML to bridge a live call

All inbound WhatsApp messages are routed to one agent and published to
whatsapp.inbound.<agent>; the agent workers do the reasoning and reply.
"""
from __future__ import annotations

import uvicorn
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field

from ..config import get_settings
from ..events.bus import Event, Streams, get_bus
from ..integrations.whatsapp import get_whatsapp
from ..integrations.voice import get_voice_provider
from ..llm.router import get_router
from ..logging import configure_logging, get_logger
from . import router as agent_router

log = get_logger("gateway")
app = FastAPI(title="AIA Gateway")


class TestMessage(BaseModel):
    agent: str = Field(pattern="^(business|health)$")
    text: str
    peer: str = "local-test"


@app.get("/health")
async def health() -> dict:
    try:
        wa = await get_whatsapp().health()
    except Exception as exc:
        wa = {"error": str(exc)}
    return {"ok": True, "whatsapp": wa}


@app.get("/models")
async def list_models() -> dict:
    """Return every model the configured Ollama server can serve.

    Includes locally-cached models and any Ollama Cloud `:cloud` models you've
    signed in for. Use the `name` field (e.g. "nemotron-3-super:cloud") as the
    value for LLM_LOCAL_MODEL / LLM_EMBEDDING_MODEL in `.env`.
    """
    settings = get_settings()
    models = await get_router().list_ollama_models()
    return {
        "base_url": settings.ollama_base_url,
        "current_local": settings.llm_local_model,
        "current_cloud": settings.llm_cloud_model,
        "current_embed": settings.llm_embedding_model,
        "models": models,
    }


@app.post("/test/message")
async def test_message(body: TestMessage) -> dict:
    """Run one agent turn directly, without WhatsApp.

    This endpoint is for local laptop testing. It exercises the same agent
    reasoning loop and tools, but returns the reply in HTTP so setup can be
    verified before pairing a WhatsApp device.
    """
    settings = get_settings()
    if settings.env != "local":
        return {"error": "test endpoint is only enabled when AIA_ENV=local"}

    if body.agent == "health":
        from ..agents.health.workflow import agent
    else:
        from ..agents.business.workflow import agent

    reply = await agent.handle_message(settings.tenant_id, body.peer, body.text)
    return {"agent": body.agent, "peer": body.peer, "reply": reply}


@app.post("/webhook/whatsapp")
async def whatsapp_inbound(req: Request) -> dict:
    """Baileys sidecar posts: {from, text, number_tag?}."""
    body = await req.json()
    peer = body.get("from", "")
    text = body.get("text", "")
    settings = get_settings()
    agent = await agent_router.route(text, number_tag=body.get("number_tag"))
    await get_bus().publish(
        f"{Streams.WHATSAPP_INBOUND}.{agent}",
        Event(type="whatsapp.message", tenant_id=settings.tenant_id,
              payload={"peer": peer, "text": text}),
    )
    return {"routed_to": agent}


@app.get("/webhook/whatsapp/cloud")
async def cloud_verify(req: Request) -> Response:
    """Meta verification handshake (hub.challenge)."""
    params = req.query_params
    expected = get_settings().whatsapp_cloud_verify_token
    if expected and params.get("hub.verify_token") == expected and params.get("hub.challenge"):
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook/whatsapp/cloud")
async def cloud_inbound(req: Request) -> dict:
    body = await req.json()
    settings = get_settings()
    try:
        msg = body["entry"][0]["changes"][0]["value"]["messages"][0]
        peer = msg["from"]
        text = msg.get("text", {}).get("body", "")
    except (KeyError, IndexError):
        return {"ignored": True}
    agent = await agent_router.route(text)
    await get_bus().publish(
        f"{Streams.WHATSAPP_INBOUND}.{agent}",
        Event(type="whatsapp.message", tenant_id=settings.tenant_id,
              payload={"peer": peer, "text": text}),
    )
    return {"routed_to": agent}


@app.post("/webhook/twilio/voice")
async def twilio_voice() -> Response:
    """Return TwiML that bridges the call to the realtime voice engine."""
    settings = get_settings()
    stream_url = settings.public_base_url.replace("http", "ws") + "/media"
    twiml = get_voice_provider().inbound_twiml(
        greeting="Hello, you've reached the assistant. How can I help?",
        stream_url=stream_url,
    )
    return Response(content=twiml, media_type="application/xml")


def main() -> None:
    configure_logging()
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
