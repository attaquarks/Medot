"""Agent Platform client: updates parsing, sends, error taxonomy, budgets.

Payloads mirror the shapes documented in Meta's WhatsApp Agent Platform
Developer Manual (and the reference implementation's test fixtures).
"""
import json

import httpx
import pytest

from medot.whatsapp.agent_platform import (
    AgentPlatformClient,
    Ambiguous,
    AuthError,
    MalformedResponse,
    NotCreatorError,
    NotSent,
    PollConflict,
    RateLimited,
    RateWindow,
    Retryable,
    parse_sha256,
    parse_updates,
    split_text,
    utf16_len,
)

CREATOR = "user:50972923564215"
WAMID = "wamid.HBg..."
UPDATE_BODY = {
    "object": "whatsapp_agent_platform",
    "entry": [
        {
            "id": "123456789",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "contacts": [{"wa_id": CREATOR, "profile": {"name": "Alex"}}],
                        "messages": [
                            {
                                "from": CREATOR,
                                "id": WAMID,
                                "timestamp": "1736844652",
                                "type": "text",
                                "text": {"body": "Hello agent"},
                            }
                        ],
                        "statuses": [],
                    },
                }
            ],
        }
    ],
    "next_offset": 1287,
}


def _client(handler) -> AgentPlatformClient:
    transport = httpx.MockTransport(handler)
    return AgentPlatformClient(
        "wapia-key-1234567890abcdef", http=httpx.AsyncClient(transport=transport)
    )


def _updates(*messages: dict, statuses: list | None = None) -> dict:
    body = json.loads(json.dumps(UPDATE_BODY))  # deep copy
    value = body["entry"][0]["changes"][0]["value"]
    value["messages"] = list(messages)
    value["statuses"] = statuses or []
    return body


def _text_message(body: str = "Hello agent", mid: str = WAMID) -> dict:
    return {"from": CREATOR, "id": mid, "timestamp": "1736844652", "type": "text", "text": {"body": body}}


async def test_get_updates_parses_message_and_advances_offset():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.whatsapp.com"
        assert request.url.path == "/agent/v1/updates"
        assert request.headers["Authorization"] == "Bearer wapia-key-1234567890abcdef"
        assert request.url.params["timeout"] == "20"
        return httpx.Response(200, json=UPDATE_BODY)

    client = _client(handler)
    updates = await client.get_updates(None)
    assert updates.next_offset == 1287
    assert len(updates.messages) == 1
    assert updates.messages[0]["text"]["body"] == "Hello agent"
    assert updates.contacts[0]["wa_id"] == CREATOR
    await client.aclose()


async def test_get_updates_204_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = _client(handler)
    updates = await client.get_updates(42)
    assert updates.next_offset is None
    assert updates.messages == []
    await client.aclose()


async def test_send_text_builds_documented_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/agent/v1/messages"
        body = json.loads(request.content)
        assert body["messaging_product"] == "whatsapp"
        assert body["to"] == CREATOR
        assert body["type"] == "text"
        assert body["text"]["body"] == "ping"
        return httpx.Response(200, json={"messages": [{"id": "wamid.OUT"}]})

    client = _client(handler)
    mid = await client.send_text(CREATOR, "ping")
    assert mid == "wamid.OUT"
    await client.aclose()


async def test_send_reply_includes_context():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["context"] == {"message_id": WAMID}
        return httpx.Response(200, json={"messages": [{"id": "wamid.OUT"}]})

    client = _client(handler)
    mid = await client.send_text(CREATOR, "re", reply_to=WAMID)
    assert mid == "wamid.OUT"
    await client.aclose()


async def test_local_status_budget_exhaustion():
    """The statuses budget is enforced locally without waiting (try_acquire)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True})

    client = _client(handler)
    for _ in range(12):
        await client.mark_read(WAMID)
    with pytest.raises(RateLimited):  # 13th receipt in the same minute
        await client.mark_read(WAMID)
    await client.aclose()


async def test_error_taxonomy():
    cases = [
        (401, {"error": {"code": 190}}, AuthError),
        (403, {"error": {"code": 131005}}, NotCreatorError),
        (429, {"error": {"code": 130429}}, RateLimited),
        (503, {"error": {"code": 131016}}, Retryable),
        (500, {"error": {"code": 2}}, Ambiguous),
        (409, {"error": {"code": 1752041}}, NotSent),  # a 409 on send is a plain rejection
    ]
    for status, payload, expected in cases:
        def handler(request: httpx.Request, _s=status, _p=payload) -> httpx.Response:
            return httpx.Response(_s, json=_p)

        client = _client(handler)
        with pytest.raises(expected):
            await client.send_text(CREATOR, "x")
        await client.aclose()


async def test_poll_conflict_only_on_updates():
    """409/1752041 maps to PollConflict for GET /updates only."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/agent/v1/updates"
        return httpx.Response(409, json={"error": {"code": 1752041}})

    client = _client(handler)
    with pytest.raises(PollConflict):
        await client.get_updates(None)
    await client.aclose()


async def test_updates_token_rejection_is_auth_error():
    """On /updates a code-100 400 means the API key was rejected."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/agent/v1/updates"
        return httpx.Response(400, json={"error": {"code": 100}})

    client = _client(handler)
    with pytest.raises(AuthError):
        await client.get_updates(None)
    await client.aclose()


async def test_204_and_malformed_updates():
    # A 2xx body that violates the envelope is MalformedResponse, not a crash.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"object": "something_else", "next_offset": 1})

    client = _client(handler)
    with pytest.raises(MalformedResponse):
        await client.get_updates(None)
    await client.aclose()


def test_parse_updates_ignores_noise():
    body = {
        "object": "whatsapp_agent_platform",
        "next_offset": 7,
        "entry": [
            {"noise": True},
            {
                "changes": [
                    {"field": "not_messages", "value": {"messages": [{"junk": True}]}},
                    {
                        "field": "messages",
                        "value": {
                            "contacts": [{"wa_id": CREATOR, "profile": {"name": "Alex"}}],
                            "messages": [_text_message()],
                            "statuses": [{"id": "wamid.1", "status": "delivered"}],
                        },
                    },
                ]
            },
        ],
    }
    response = httpx.Response(200, json=body)
    updates = parse_updates(response)
    assert updates.next_offset == 7
    assert len(updates.messages) == 1
    assert len(updates.statuses) == 1
    assert updates.contacts[0]["profile"]["name"] == "Alex"


def test_parse_updates_rejects_missing_offset():
    response = httpx.Response(200, json={"object": "whatsapp_agent_platform", "entry": []})
    with pytest.raises(MalformedResponse):
        parse_updates(response)


async def test_mark_read_ok_and_failure():
    def ok_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["status"] == "read"
        assert body["message_id"] == WAMID
        assert body["typing_indicator"] == {"type": "text"}
        return httpx.Response(200, json={"success": True})

    client = _client(ok_handler)
    await client.mark_read(WAMID, typing=True)
    await client.aclose()

    def bad_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False})

    client = _client(bad_handler)
    with pytest.raises(MalformedResponse):
        await client.mark_read(WAMID)
    await client.aclose()


def test_split_text_respects_utf16_limit():
    # 4096 UTF-16 units: BMP chars count as 1, astral (emoji) as 2.
    bmp = "a" * 4096
    assert split_text(bmp) == [bmp]
    emoji = "🙂" * 2048  # 4096 units exactly
    assert len(split_text(emoji)) == 1
    long = "word " * 1200
    chunks = split_text(long)
    assert all(utf16_len(c) <= 4096 for c in chunks)
    assert len(chunks) > 1
    assert "".join(c for c in chunks) == long


def test_parse_sha256_accepts_hex_and_base64():
    digest_hex = "ab" * 32
    assert parse_sha256(digest_hex) == bytes.fromhex(digest_hex)
    import base64
    import hashlib

    raw = hashlib.sha256(b"x").digest()
    b64 = base64.b64encode(raw).decode()
    assert parse_sha256(b64) == raw
    assert parse_sha256(base64.urlsafe_b64encode(raw).decode()) == raw
    with pytest.raises(ValueError):
        parse_sha256("not-a-digest")


async def test_media_get_and_upload():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.startswith("/agent/v1/media/"):
            assert "lookaside" not in request.url.path
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.fbsbx.com/agent/v1/media/uuid/content",
                    "mime_type": "application/pdf",
                    "sha256": "ab" * 32,
                    "file_size": 4,
                },
            )
        if request.method == "POST" and request.url.path == "/agent/v1/media":
            assert "multipart/form-data" in request.headers["content-type"]
            return httpx.Response(200, json={"id": "8f3a2b91-5c47-4e0d-9a6b-1d2e3f4a5b6c"})
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    client = _client(handler)
    info = await client.get_media("8f3a2b91-5c47-4e0d-9a6b-1d2e3f4a5b6c")
    assert info.file_size == 4
    assert info.mime_type == "application/pdf"
    media_id = await client.upload_media(b"data", mime="image/jpeg", filename="photo.jpg")
    assert media_id == "8f3a2b91-5c47-4e0d-9a6b-1d2e3f4a5b6c"
    await client.aclose()


async def test_send_media_and_media_gone():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body.get("image", {}).get("id") == "GOODID1":
            return httpx.Response(200, json={"messages": [{"id": "wamid.M"}]})
        return httpx.Response(
            400,
            json={"error": {"code": 131009, "error_data": {"details": "No media found"}}},
        )

    client = _client(handler)
    mid = await client.send_media(CREATOR, "image", "GOODID1", caption="look")
    assert mid == "wamid.M"
    from medot.whatsapp.agent_platform import MediaGone

    with pytest.raises(MediaGone):
        await client.send_media(CREATOR, "image", "BADID99")
    await client.aclose()


def test_rate_window_penalize_fills_window():
    now = 0.0

    def clock() -> float:
        return now

    window = RateWindow(3, clock=clock)
    assert window.try_acquire()
    assert window.try_acquire()
    assert window.try_acquire()
    assert not window.try_acquire()
    window.penalize(30)
    assert window.delay() == pytest.approx(30.0)
