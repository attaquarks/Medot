"""Inbound gateway (FastAPI):  python -m aia.gateway.main

Endpoints:
  GET  /health                      liveness + WhatsApp transport status
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

from ..config import get_settings
from ..events.bus import Event, Streams, get_bus
from ..integrations.whatsapp import get_whatsapp
from ..integrations.voice import get_voice_provider
from ..logging import configure_logging, get_logger
from . import router as agent_router

log = get_logger("gateway")
app = FastAPI(title="AIA Gateway")


@app.get("/health")
async def health() -> dict:
    try:
        wa = await get_whatsapp().health()
    except Exception as exc:
        wa = {"error": str(exc)}
    return {"ok": True, "whatsapp": wa}


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
    if params.get("hub.verify_token") and params.get("hub.challenge"):
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
