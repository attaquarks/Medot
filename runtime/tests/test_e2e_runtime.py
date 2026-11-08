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
                    length = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(length) or b"{}") if length else {}
                    outer.last_body = body
                    msgs = body.get("messages", [])
                    # gate on the CURRENT message only — history from earlier
                    # tests must not trigger the forget tool call
                    user_texts = [str(m.get("content", "")) for m in msgs if m.get("role") == "user"]
                    asked_to_forget = bool(user_texts) and "forget" in user_texts[-1].lower()
                    asked_to_log = bool(user_texts) and "log my weight" in user_texts[-1].lower()
                    tool_ran = any(m.get("role") == "tool" for m in msgs)
                    tool_call = None
                    if asked_to_forget and not tool_ran:
                        tool_call = ("forget_fact", {"match": "the thing"})
                    elif asked_to_log and not tool_ran:
                        tool_call = ("save_record", {
                            "type_key": "health.weight_measurement",
                            "data": {"weight_kg": 74.2},
                            "domain": "global",
                        })
                    if tool_call:
                        self._send({
                            "choices": [{"message": {
                                "role": "assistant", "content": None,
                                "tool_calls": [{
                                    "id": "call_1", "type": "function",
                                    "function": {"name": tool_call[0], "arguments": json.dumps(tool_call[1])},
                                }],
                            }}],
                        })
                    elif tool_ran:
                        reply = "Logged it." if asked_to_log else "Done — forgot it."
                        self._send({"choices": [{"message": {"content": reply}}]})
                    else:
                        self._send({"choices": [{"message": {"content": "OK"}}]})
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



def _header(headers: dict | None, name: str) -> str | None:
    """httpx lowercases header names on the wire — look up case-insensitively."""
    if not headers:
        return None
    lowered = {k.lower(): v for k, v in headers.items()}
    return lowered.get(name.lower())

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
    output: list[str] = []

    def _drain():
        for line in proc.stdout:
            output.extend((line,))

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

    # the handshake prints BEFORE uvicorn binds — poll /health until reachable
    reachable = False
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                reachable = True
                break
        except Exception:
            time.sleep(0.25)
    if not reachable:
        proc.terminate()
        raise RuntimeError(f"runtime never became reachable; output: {output[-30:]}")

    threading.Thread(target=_drain, daemon=True).start()

    client = httpx.Client(
        base_url=f"http://127.0.0.1:{port}",
        headers={"X-Launch-Token": token},
        timeout=30,
    )
    yield client, session["user"]["id"], email, admin, output
    client.close()
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    try:
        admin.auth.admin.delete_user(session["user"]["id"])
    except Exception as exc:  # the stack dies with the runner; cleanup is best effort
        print(f"cleanup: user delete skipped ({exc})")


def test_session_is_authenticated(runtime):
    client, user_id, _email, _admin, _output = runtime
    response = client.get("/session")
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert response.json()["user_id"] == user_id


def test_discover_fetches_live_models(runtime, mock_provider):
    client, _user_id, _email, _admin, _output = runtime
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
    assert _header(mock_provider.last_model_request, "Authorization") == "Bearer sk-e2e"


def test_profile_save_verify_list_delete_end_to_end(runtime, mock_provider):
    client, _user_id, _email, _admin, _output = runtime
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
    assert _header(mock_provider.last_completion, "Authorization") == "Bearer sk-e2e"

    # the profile is visible RLS-scoped through a user JWT
    listing = client.get("/providers/profiles")
    assert listing.status_code == 200
    assert [p["model"] for p in listing.json()["profiles"]] == ["mock-large"]
    assert all("sk-e2e" not in str(p) for p in listing.json()["profiles"])

    # (cross-user isolation for model_profiles is covered by the RLS suite)

    # delete clears the row and the keystore-backed credential
    deleted = client.delete(f"/providers/profiles/{profile_id}")
    assert deleted.status_code == 200
    assert client.get("/providers/profiles").json()["profiles"] == []


def test_engine_test_turn_end_to_end(runtime, mock_provider):
    """Talk to Me. from the desktop: a REAL engine turn — LangGraph graph,
    real litellm completion against the live mock provider, real persistence."""
    client, _user_id, email, admin, output = runtime
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
    assert turn.status_code == 200, f"engine turn failed: {turn.text[:400]}"
    assert "OK" in turn.json()["reply"]
    assert _header(mock_provider.last_completion, "Authorization") == "Bearer sk-e2e"

    # the exchange is persisted, RLS-scoped: the desktop conversation has the
    # user's message and Me.'s reply
    from supabase import create_client

    as_user = create_client(os.environ["MEDOT_TEST_SUPABASE_URL"], os.environ["MEDOT_TEST_SUPABASE_KEY"])
    as_user.postgrest.auth(
        admin.auth.sign_in_with_password(
            {"email": email, "password": "S3cret-Pass!"}
        ).session.access_token
    )
    conversation = as_user.table("conversations").select("id").eq("peer", "desktop").execute().data
    assert conversation, "desktop conversation missing"
    rows = as_user.table("messages").select("direction,body").eq("conversation_id", conversation[0]["id"]).execute().data
    assert sorted(r["direction"] for r in rows) == ["inbound", "outbound"], (
        f"messages: {rows} | admin: {admin.table('messages').select('direction,body').execute().data} | runtime: {output[-15:]}")
    assert any(r["body"] == "Reply with exactly: OK" for r in rows)



def test_engine_tool_approval_loop_end_to_end(runtime, mock_provider):
    """The full M4b loop, for real: Me. decides to use a destructive tool →
    interrupt → approval row → the user's YES resumes it → run closes."""
    client, _user_id, email, admin, output = runtime
    base = f"http://127.0.0.1:{mock_provider.server_address[1]}/v1"
    saved = client.post(
        "/providers/profiles",
        json={"name": "E2E Chat", "purpose": "chat", "provider": "openai_compatible",
              "model": "mock-large", "api_base": base, "api_key": "sk-e2e"},
    )
    assert saved.status_code == 200

    # turn 1: the model calls forget_fact → the flow interrupts and proposes
    turn = client.post("/engine/test-turn", json={"text": "please forget the thing"})
    assert turn.status_code == 200, f"engine turn failed: {turn.text[:400]}"
    assert "YES" in turn.json()["reply"], turn.json()

    # the approval is pending, RLS-scoped, with the thread id for resume
    from supabase import create_client

    as_user = create_client(os.environ["MEDOT_TEST_SUPABASE_URL"], os.environ["MEDOT_TEST_SUPABASE_KEY"])
    as_user.postgrest.auth(
        admin.auth.sign_in_with_password({"email": email, "password": "S3cret-Pass!"}).session.access_token
    )
    approvals = as_user.table("approvals").select("id,status,action,payload").execute().data
    admin_rows = admin.table("approvals").select("id,status,action,payload,user_id").execute().data
    assert len(approvals) == 1 and approvals[0]["status"] == "pending", (
        f"approvals(rls): {approvals} | approvals(admin): {admin_rows} | runtime: {output[-15:]}")
    assert approvals[0]["action"] == "forget_fact"
    assert approvals[0]["payload"]["peer"] == "desktop"

    # turn 2: the user's YES resumes the exact same thread; the tool executes
    decision = client.post("/engine/test-turn", json={"text": "YES"})
    assert decision.status_code == 200
    approvals_now = as_user.table("approvals").select("id,status,payload").execute().data
    assert "forgot" in decision.json()["reply"].lower() or "Done" in decision.json()["reply"], (
        f"reply: {decision.json()} | approvals: {approvals_now} | runtime: {output[-15:]}")

    approvals_after = as_user.table("approvals").select("status").execute().data
    assert approvals_after[0]["status"] == "approved"
    runs = as_user.table("agent_runs").select("status").execute().data
    assert any(r["status"] == "succeeded" for r in runs)


def test_engine_retrieves_knowledge_into_prompt(runtime, mock_provider):
    """M3b, for real: a fact remembered about the user's life reaches the
    model's system prompt on the next turn (runtime → RLS query → prompt)."""
    client, user_id, email, admin, _output = runtime
    saved = client.post(
        "/providers/profiles",
        json={"name": "E2E Chat", "purpose": "chat", "provider": "openai_compatible",
              "model": "mock-large", "api_base": f"http://127.0.0.1:{mock_provider.server_address[1]}/v1",
              "api_key": "sk-e2e"},
    )
    assert saved.status_code == 200

    from supabase import create_client

    as_user = create_client(os.environ["MEDOT_TEST_SUPABASE_URL"], os.environ["MEDOT_TEST_SUPABASE_KEY"])
    as_user.postgrest.auth(
        admin.auth.sign_in_with_password({"email": email, "password": "S3cret-Pass!"}).session.access_token
    )
    node = (
        as_user.table("knowledge_nodes")
        .insert({"user_id": user_id, "node_type": "entity", "name": "Priya",
                 "summary": "the user's sister, allergic to peanuts"})
        .execute()
        .data
    )
    assert node, "knowledge node insert failed (RLS?)"

    turn = client.post("/engine/test-turn", json={"text": "What can I cook for Priya?"})
    assert turn.status_code == 200, f"engine turn failed: {turn.text[:400]}"
    assert "OK" in turn.json()["reply"], f"expected a completed turn: {turn.json()}"

    system = next(m for m in mock_provider.last_body["messages"] if m["role"] == "system")
    assert "What you remember that may be relevant here:" in system["content"], system["content"][:600]
    assert "Priya — the user's sister, allergic to peanuts" in system["content"], system["content"][:600]


def test_identity_registry_end_to_end(runtime):
    """M2b, for real: create a specialist, list (Me. seeded by the DB trigger),
    save a new instruction version, deactivate — all through the runtime API."""
    client, _user_id, _email, _admin, _output = runtime
    created = client.post("/identities", json={
        "name": "Garden Coach",
        "instructions_md": "You help with the garden. Be practical.",
        "description": "plants and beds",
    })
    assert created.status_code == 200, created.text
    identity = created.json()
    assert identity["slug"] == "garden-coach"
    assert identity["instructions_version"] == 1

    listing = client.get("/identities")
    assert listing.status_code == 200
    ids = {i["slug"]: i for i in listing.json()["identities"]}
    assert "me" in ids, "the signup trigger must have seeded Me."
    assert ids["garden-coach"]["instructions_md"] == "You help with the garden. Be practical."

    saved = client.put(f"/identities/{identity['id']}/instructions", json={"content_md": "v2 instructions"})
    assert saved.status_code == 200 and saved.json()["version"] == 2

    patched = client.patch(f"/identities/{identity['id']}", json={"status": "deactivated"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "deactivated"

    bad_status = client.patch(f"/identities/{identity['id']}", json={"status": "zombie"})
    assert bad_status.status_code == 400
    missing = client.patch("/identities/00000000-0000-0000-0000-000000000000", json={"status": "active"})
    assert missing.status_code == 404


def test_engine_slug_routes_to_specialist_end_to_end(runtime, mock_provider):
    """M2b payoff, for real: '/herb-coach ...' routes the turn to that
    identity — its instructions and its bound model profile drive the model."""
    client, _user_id, email, admin, _output = runtime
    base = f"http://127.0.0.1:{mock_provider.server_address[1]}/v1"
    saved = client.post(
        "/providers/profiles",
        json={"name": "E2E Chat", "purpose": "chat", "provider": "openai_compatible",
              "model": "mock-large", "api_base": base, "api_key": "sk-e2e"},
    )
    assert saved.status_code == 200
    profile_id = saved.json()["id"]

    created = client.post("/identities", json={
        "name": "Herb Coach",
        "instructions_md": "You advise on herbs. Always mention soil.",
    })
    assert created.status_code == 200, created.text
    assert created.json()["slug"] == "herb-coach"
    identity_id = created.json()["id"]
    bound = client.patch(f"/identities/{identity_id}", json={"model_profile_id": profile_id})
    assert bound.status_code == 200

    turn = client.post("/engine/test-turn", json={"text": "/herb-coach what should I plant?"})
    assert turn.status_code == 200, f"engine turn failed: {turn.text[:400]}"

    listing = client.get("/identities")
    rows = {i["slug"]: i for i in listing.json()["identities"]}
    herb = {k: rows.get("herb-coach", {}).get(k) for k in ("status", "model_profile_id")}
    diag = (
        f"reply: {turn.json()['reply'][:200]} | herb row: {herb} | identities: "
        f"{[(i['slug'], i['status']) for i in listing.json()['identities']]} | runtime: {_output[-15:]}"
    )

    system = next(m for m in mock_provider.last_body["messages"] if m["role"] == "system")
    assert "You advise on herbs. Always mention soil." in system["content"], (
        f"DIAG {diag} | system: {system['content'][:300]}"
    )

    from supabase import create_client

    as_user = create_client(os.environ["MEDOT_TEST_SUPABASE_URL"], os.environ["MEDOT_TEST_SUPABASE_KEY"])
    as_user.postgrest.auth(
        admin.auth.sign_in_with_password({"email": email, "password": "S3cret-Pass!"}).session.access_token
    )
    runs = as_user.table("agent_runs").select("status,identity_id").execute().data
    assert any(r["identity_id"] == identity_id and r["status"] == "succeeded" for r in runs), runs

    unknown = client.post("/engine/test-turn", json={"text": "/nobody hi"})
    assert unknown.status_code == 200
    assert "specialist" in unknown.json()["reply"].lower(), unknown.json()


def test_console_approve_decide_end_to_end(runtime, mock_provider):
    """The console's Approve button: a pending approval decided through
    POST /approvals/{id}/decide resumes the same run, like a WhatsApp YES."""
    client, _user_id, email, admin, _output = runtime

    turn = client.post("/engine/test-turn", json={"text": "please forget the thing"})
    assert turn.status_code == 200, f"engine turn failed: {turn.text[:400]}"
    assert "YES" in turn.json()["reply"], turn.json()

    listing = client.get("/approvals")
    assert listing.status_code == 200, listing.text
    pending = listing.json()["pending"]
    assert len(pending) == 1 and pending[0]["action"] == "forget_fact", pending

    decided = client.post(f"/approvals/{pending[0]['id']}/decide", json={"approved": True})
    assert decided.status_code == 200, decided.text
    assert "forgot" in decided.json()["reply"].lower(), decided.json()

    decided_again = client.post(f"/approvals/{pending[0]['id']}/decide", json={"approved": False})
    assert decided_again.status_code == 409, decided_again.text

    feed = client.get("/activity")
    assert feed.status_code == 200, feed.text
    events = feed.json()["events"]
    assert any(e["event"] == "approval.decided" for e in events), events

    from supabase import create_client

    as_user = create_client(os.environ["MEDOT_TEST_SUPABASE_URL"], os.environ["MEDOT_TEST_SUPABASE_KEY"])
    as_user.postgrest.auth(
        admin.auth.sign_in_with_password({"email": email, "password": "S3cret-Pass!"}).session.access_token
    )
    statuses = as_user.table("approvals").select("status").execute().data
    assert any(s["status"] == "approved" for s in statuses), statuses
    runs = as_user.table("agent_runs").select("status").execute().data
    assert any(r["status"] == "succeeded" for r in runs), runs


def test_knowledge_screen_end_to_end(runtime, mock_provider):
    """M3, for real: a remembered fact shows up in the Knowledge reads the
    console makes — overview counts, area detail, records browser."""
    client, user_id, email, admin, _output = runtime

    from supabase import create_client

    as_user = create_client(os.environ["MEDOT_TEST_SUPABASE_URL"], os.environ["MEDOT_TEST_SUPABASE_KEY"])
    as_user.postgrest.auth(
        admin.auth.sign_in_with_password({"email": email, "password": "S3cret-Pass!"}).session.access_token
    )
    domain_id = as_user.table("knowledge_domains").select("id").eq("slug", "global").limit(1).execute().data[0]["id"]
    node = as_user.table("knowledge_nodes").insert({
        "user_id": user_id, "domain_id": domain_id, "node_type": "entity",
        "name": "Priya", "summary": "the user's sister",
    }).execute().data[0]
    as_user.table("knowledge_edges").insert({
        "user_id": user_id, "domain_id": domain_id,
        "src_node_id": node["id"], "dst_node_id": node["id"],
        "relation": "is allergic to", "fact": "Priya is allergic to peanuts",
    }).execute()

    overview = client.get("/knowledge")
    assert overview.status_code == 200, overview.text
    domains = {d["slug"]: d for d in overview.json()["domains"]}
    assert "global" in domains, domains
    assert domains["global"]["facts"] >= 1 and domains["global"]["topics"] >= 1, domains["global"]

    detail = client.get(f"/knowledge/domains/{domain_id}")
    assert detail.status_code == 200, detail.text
    facts = [f["fact"] for f in detail.json()["facts"]]
    assert "Priya is allergic to peanuts" in facts, facts
    topics = [t["name"] for t in detail.json()["topics"]]
    assert "Priya" in topics, topics

    records = client.get(f"/knowledge/domains/{domain_id}/records")
    assert records.status_code == 200 and records.json()["records"] == [], records.text

    missing = client.get("/knowledge/domains/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


def test_record_capture_end_to_end(runtime, mock_provider):
    """M3 record capture, for real: 'log my weight' -> the model calls
    save_record -> a schema-validated domain_record row the Knowledge
    screen's records browser serves back."""
    client, _user_id, email, admin, _output = runtime

    turn = client.post("/engine/test-turn", json={"text": "please log my weight 74.2"})
    assert turn.status_code == 200, f"engine turn failed: {turn.text[:400]}"
    assert "logged" in turn.json()["reply"].lower(), turn.json()

    from supabase import create_client

    as_user = create_client(os.environ["MEDOT_TEST_SUPABASE_URL"], os.environ["MEDOT_TEST_SUPABASE_KEY"])
    as_user.postgrest.auth(
        admin.auth.sign_in_with_password({"email": email, "password": "S3cret-Pass!"}).session.access_token
    )
    rows = as_user.table("domain_records").select("type_key,data,domain_id").execute().data
    assert rows and rows[0]["type_key"] == "health.weight_measurement", rows
    assert rows[0]["data"] == {"weight_kg": 74.2}, rows

    domain_id = rows[0]["domain_id"]
    served = client.get(f"/knowledge/domains/{domain_id}/records")
    assert served.status_code == 200, served.text
    records = served.json()["records"]
    assert records and records[0]["type_title"] == "Weight measurement", records
    assert records[0]["data"] == {"weight_kg": 74.2}, records


@pytest.fixture(scope="module")
def mcp_dice_server():
    """A REAL MCP server (streamable-HTTP) running inside the test process."""
    import threading

    from mcp.server.mcpserver import MCPServer

    calls: list[int] = []
    server = MCPServer("medot-e2e-dice")

    @server.tool()
    def roll_dice(sides: int = 6) -> str:
        calls.append(sides)
        return f"rolled a {sides}-sider: it landed on 4"

    port = _free_port(MOCK_PORT + 200)
    url = f"http://127.0.0.1:{port}/mcp"

    def _serve():
        import asyncio

        asyncio.run(server.run_streamable_http_async(host="127.0.0.1", port=port, stateless_http=True))

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    import time as _time

    for _ in range(60):
        try:
            httpx.post(url, json={"jsonrpc": "2.0", "method": "ping", "id": 1}, timeout=1)
            break
        except Exception:
            _time.sleep(0.25)
    yield url, calls


def test_connector_mcp_end_to_end(runtime, mock_provider, mcp_dice_server):
    """M7, for real: one-click add a connector pointing at a live MCP server,
    list its tools, then a real conversation turn executes its tool."""
    client, _user_id, _email, _admin, _output = runtime
    url, calls = mcp_dice_server
    saved = client.post(
        "/providers/profiles",
        json={"name": "E2E Chat", "purpose": "chat", "provider": "openai_compatible",
              "model": "mock-large", "api_base": f"http://127.0.0.1:{mock_provider.server_address[1]}/v1",
              "api_key": "sk-e2e"},
    )
    assert saved.status_code == 200

    catalog = client.get("/connectors/catalog")
    assert catalog.status_code == 200
    assert any(c["key"] == "github" for c in catalog.json()["catalog"])

    created = client.post("/connectors", json={"provider": "dice", "account_label": "Dice", "url": url})
    assert created.status_code == 200, created.text
    connector_id = created.json()["id"]

    tested = client.post(f"/connectors/{connector_id}/test")
    assert tested.status_code == 200, tested.text
    assert tested.json()["ok"] is True and "roll_dice" in tested.json()["tools"], tested.json()

    bad = client.post("/connectors", json={"provider": "nope", "url": "http://127.0.0.1:1/mcp"})
    assert bad.status_code == 200  # creation succeeds; the test button catches dead servers
    dead_test = client.post(f"/connectors/{bad.json()['id']}/test")
    assert dead_test.status_code == 200 and dead_test.json()["ok"] is False, dead_test.text

    turn = client.post("/engine/test-turn", json={"text": "please roll a dice"})
    assert turn.status_code == 200, f"engine turn failed: {turn.text[:400]}"
    assert "rolled" in turn.json()["reply"].lower(), turn.json()
    assert calls == [6], f"the MCP tool must have executed server-side: {calls}"

    listing = client.get("/connectors")
    assert [c["enabled"] for c in listing.json()["connectors"]] == [True, True]

    deleted = client.delete(f"/connectors/{connector_id}")
    assert deleted.status_code == 200
    gone = client.post(f"/connectors/{connector_id}/test")
    assert gone.status_code == 404
