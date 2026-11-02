"""Real-environment end-to-end: runtime process + Supabase + a live mock provider.

Gated: runs only when MEDOT_E2E=1 and a Supabase stack is reachable (the CI
`supabase` job). Everything here is real — a real runtime subprocess, real
loopback HTTP, real Supabase rows under RLS, and a real LiteLLM completion
against a live OpenAI-compatible mock server. No doubles on the paths under
test.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from conftest import supabase_available

pytestmark = [
    pytest.mark.skipif(os.environ.get("MEDOT_E2E") != "1", reason="e2e runs only with MEDOT_E2E=1"),
    pytest.mark.skipif(not supabase_available(), reason="no reachable Supabase stack"),
]

RUNTIME_PORT = 8799
MOCK_PORT = 18901


def _free_port(base: int) -> int:
    for port in range(base, base + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free port")


class _MockProvider(ThreadingHTTPServer):
    """OpenAI-compatible /v1/models + /v1/chat/completions on localhost."""

    def __init__(self, port: int):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, payload: dict, status: int = 200):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path.endswith("/models"):
                    outer.last_model_request = dict(self.headers)
                    self._send({"data": [{"id": "mock-large"}, {"id": "mock-mini"}]})
                else:
                    self._send({"error": "not found"}, 404)

            def do_POST(self):
                if self.path.endswith("/chat/completions"):
                    outer.last_completion = dict(self.headers)
                    self._send({
                        "choices": [{"message": {"content": "OK"}}],
                        "usage": {"total_tokens": 5},
                    })
                else:
                    self._send({"error": "not found"}, 404)

            def log_message(self, *a):
                pass

        super().__init__(("127.0.0.1", port), Handler)


@pytest.fixture(scope="module")
def mock_provider():
    server = _MockProvider(_free_port(MOCK_PORT))
    server.last_completion = None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def _admin():
    from supabase import create_client

    return create_client(
        os.environ["MEDOT_TEST_SUPABASE_URL"], os.environ["MEDOT_TEST_SUPABASE_SERVICE_KEY"]
    )


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    """The real runtime process, signed in as a real throwaway Supabase user."""
    admin = _admin()
    email = f"medot-e2e-{uuid.uuid4().hex[:10]}@example.com"
    admin.auth.admin.create_user({"email": email, "password": "S3cret-Pass!", "email_confirm": True})
    session = (
        admin.auth.sign_in_with_password({"email": email, "password": "S3cret-Pass!"}).model_dump()
    )

    port = _free_port(RUNTIME_PORT)
    data_dir = tmp_path_factory.mktemp("medot-e2e")
    env = {
        **os.environ,
        "MEDOT_API_PORT": str(port),
        "MEDOT_DATA_DIR": str(data_dir),
        "MEDOT_KEYSTORE": "memory",  # test-only: CI has no OS keystore
        "MEDOT_TEST_SESSION_BLOB": json.dumps({
            "user": {"id": session["user"]["id"]},
            "access_token": session["session"]["access_token"],
            "expires_at": session["session"]["expires_at"],
        }),
        "MEDOT_SUPABASE_URL": os.environ["MEDOT_TEST_SUPABASE_URL"],
        "MEDOT_SUPABASE_PUBLISHABLE_KEY": os.environ["MEDOT_TEST_SUPABASE_KEY"],
    }
    runtime_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    proc = subprocess.Popen(
        [sys.executable, "-m", "medot"],
        cwd=runtime_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    token = None
    deadline = time.time() + 30
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        try:
            payload = json.loads(line.strip())
        except ValueError:
            continue
        if payload.get("event") == "runtime_ready":
            token = payload["launch_token"]
            break
    if not token:
        proc.terminate()
        raise RuntimeError("runtime did not report ready")

    client = httpx.Client(
        base_url=f"http://127.0.0.1:{port}",
        headers={"X-Launch-Token": token},
        timeout=30,
    )
    yield client, session["user"]["id"], admin
    client.close()
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    admin.auth.admin.delete_user(session["user"]["id"])


def test_session_is_authenticated(runtime):
    client, user_id, _admin = runtime
    response = client.get("/session")
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert response.json()["user_id"] == user_id


def test_discover_fetches_live_models(runtime, mock_provider):
    client, _user_id, _admin = runtime
    response = client.post(
        "/providers/discover",
        json={
            "provider": "openai_compatible",
            "base_url": f"http://127.0.0.1:{mock_provider.server_address[1]}/v1",
            "api_key": "sk-e2e",
        },
    )
    assert response.status_code == 200
    assert "mock-large" in response.json()["models"]
    assert mock_provider.last_model_request.get("Authorization") == "Bearer sk-e2e"


def test_profile_save_verify_list_delete_end_to_end(runtime, mock_provider):
    client, _user_id, admin = runtime
    base = f"http://127.0.0.1:{mock_provider.server_address[1]}/v1"

    saved = client.post(
        "/providers/profiles",
        json={
            "name": "E2E Main",
            "purpose": "chat",
            "provider": "openai_compatible",
            "model": "mock-large",
            "api_base": base,
            "api_key": "sk-e2e",
        },
    )
    assert saved.status_code == 200
    profile_id = saved.json()["id"]

    # verify = a REAL litellm completion through the real runtime to the live mock
    verified = client.post(f"/providers/profiles/{profile_id}/verify")
    assert verified.status_code == 200
    body = verified.json()
    assert body["ok"] is True
    assert body["sample"] == "OK"
    assert body["model_string"] == "openai/mock-large"
    assert mock_provider.last_completion.get("Authorization") == "Bearer sk-e2e"

    # the profile is visible RLS-scoped through a user JWT
    listing = client.get("/providers/profiles")
    assert listing.status_code == 200
    assert [p["model"] for p in listing.json()["profiles"]] == ["mock-large"]
    assert all("sk-e2e" not in str(p) for p in listing.json()["profiles"])

    # cross-user isolation: another user sees nothing
    other_email = f"medot-e2e-other-{uuid.uuid4().hex[:8]}@example.com"
    admin.auth.admin.create_user({"email": other_email, "password": "S3cret-Pass!", "email_confirm": True})
    other = admin.auth.sign_in_with_password({"email": other_email, "password": "S3cret-Pass!"})
    from supabase import create_client

    other_client = create_client(os.environ["MEDOT_TEST_SUPABASE_URL"], os.environ["MEDOT_TEST_SUPABASE_KEY"])
    other_client.postgrest.auth(other.session.access_token)
    rows = other_client.table("model_profiles").select("id").execute().data
    assert rows == []
    admin.auth.admin.delete_user(other.user.id)

    # delete clears the row and the keystore-backed credential
    deleted = client.delete(f"/providers/profiles/{profile_id}")
    assert deleted.status_code == 200
    assert client.get("/providers/profiles").json()["profiles"] == []


def test_engine_test_turn_end_to_end(runtime, mock_provider):
    """Talk to Me. from the desktop: a REAL engine turn — LangGraph graph,
    real litellm completion against the live mock provider, real persistence."""
    client, _user_id, admin = runtime
    base = f"http://127.0.0.1:{mock_provider.server_address[1]}/v1"
    saved = client.post(
        "/providers/profiles",
        json={
            "name": "E2E Chat",
            "purpose": "chat",
            "provider": "openai_compatible",
            "model": "mock-large",
            "api_base": base,
            "api_key": "sk-e2e",
        },
    )
    assert saved.status_code == 200

    turn = client.post("/engine/test-turn", json={"text": "Reply with exactly: OK"})
    assert turn.status_code == 200
    assert "OK" in turn.json()["reply"]
    assert mock_provider.last_completion.get("Authorization") == "Bearer sk-e2e"

    # the exchange is persisted, RLS-scoped: the desktop conversation has the
    # user's message and Me.'s reply
    from supabase import create_client

    as_user = create_client(os.environ["MEDOT_TEST_SUPABASE_URL"], os.environ["MEDOT_TEST_SUPABASE_KEY"])
    as_user.postgrest.auth(
        admin.auth.sign_in_with_password(
            {"email": _runtime_email(admin), "password": "S3cret-Pass!"}
        ).session.access_token
    )
    conversation = as_user.table("conversations").select("id").eq("peer", "desktop").execute().data
    assert conversation, "desktop conversation missing"
    rows = as_user.table("messages").select("direction,body").eq("conversation_id", conversation[0]["id"]).execute().data
    directions = sorted(r["direction"] for r in rows)
    assert directions == ["inbound", "outbound"]
    assert any(r["body"] == "Reply with exactly: OK" for r in rows)


def _runtime_email(admin) -> str:
    # the module fixture created one user; find it by listing recent users
    users = admin.auth.admin.list_user().users
    match = [u for u in users if u.email and u.email.startswith("medot-e2e-") and "other" not in u.email]
    assert match, "runtime user not found"
    return match[0].email
