"""Supabase integration tests — run against a real (local or hosted) stack.

Gated: skipped unless MEDOT_TEST_SUPABASE_URL / _KEY point at a reachable
stack (local: `supabase start`, http://127.0.0.1:54321). Uses the admin API
(service key) ONLY to create/delete throwaway test users — the assertions
themselves run strictly as the authenticated users (anon key + JWT).
"""
import os
import uuid

import pytest
from conftest import supabase_available

pytestmark = pytest.mark.skipif(
    not supabase_available(), reason="no reachable Supabase stack for integration tests"
)

USER_TABLES = [
    "profiles", "user_settings", "model_profiles", "identities",
    "identity_instructions", "knowledge_domains", "knowledge_nodes",
    "knowledge_edges", "memory_episodes", "domain_records", "conversations",
    "messages", "agent_runs", "approvals", "activity_events",
    "connector_accounts", "identity_tool_grants", "identity_connector_grants",
    "memory_embeddings_768", "memory_embeddings_1024", "memory_embeddings_1536",
]


def _admin():
    from supabase import create_client

    return create_client(
        os.environ["MEDOT_TEST_SUPABASE_URL"], os.environ["MEDOT_TEST_SUPABASE_SERVICE_KEY"]
    )


def _as_user(url: str, key: str, email: str, password: str):
    """Sign in a throwaway user; return (client-as-user, user_id)."""
    from supabase import create_client

    client = create_client(url, key)
    res = client.auth.sign_in_with_password({"email": email, "password": password})
    user_id = res.user.id
    client.postgrest.auth(res.session.access_token)
    return client, user_id


@pytest.fixture(scope="module")
def two_users():
    url = os.environ["MEDOT_TEST_SUPABASE_URL"]
    key = os.environ["MEDOT_TEST_SUPABASE_KEY"]
    admin = _admin()
    users = []
    for i in range(2):
        email = f"medot-test-{uuid.uuid4().hex[:10]}@example.com"
        admin.auth.admin.create_user({"email": email, "password": "S3cret-Pass!", "email_confirm": True})
        users.append(_as_user(url, key, email, "S3cret-Pass!"))
    yield users
    for _, uid in users:
        admin.auth.admin.delete_user(uid)


def test_signup_trigger_initializes_account(two_users):
    """AC2: profile + settings + Me. identity + v1 instructions + global domain."""
    (client_a, user_a), _ = two_users
    profile = (client_a.table("profiles").select("*").eq("id", user_a).execute()).data
    assert len(profile) == 1
    settings = (client_a.table("user_settings").select("*").eq("user_id", user_a).execute()).data
    assert len(settings) == 1
    me = (client_a.table("identities").select("*")
          .eq("user_id", user_a).eq("slug", "me").eq("kind", "coordinator").execute()).data
    assert len(me) == 1
    instructions = (client_a.table("identity_instructions")
                    .select("*").eq("identity_id", me[0]["id"]).execute()).data
    assert len(instructions) == 1 and instructions[0]["version"] == 1
    domain = (client_a.table("knowledge_domains").select("*")
              .eq("user_id", user_a).eq("slug", "global").execute()).data
    assert len(domain) == 1 and me[0]["domain_id"] == domain[0]["id"]


def test_rls_cross_user_isolation(two_users):
    """AC3: user B sees ZERO rows of user A across every user-owned table."""
    (client_a, user_a), (client_b, _user_b) = two_users

    # Seed a row for A wherever a synthetic row is insertable.
    client_a.table("identities").insert({
        "user_id": user_a, "kind": "specialist", "name": "Gardening", "slug": f"gardening-{uuid.uuid4().hex[:6]}",
    }).execute()
    client_a.table("knowledge_domains").insert({
        "user_id": user_a, "slug": f"gardening-{uuid.uuid4().hex[:6]}", "title": "Gardening",
    }).execute()

    for table in USER_TABLES:
        res = client_b.table(table).select("*").execute()
        rows = [r for r in (res.data or []) if r.get("user_id") == user_a or r.get("id") == user_a]
        assert rows == [], f"RLS leak: user B sees user A rows in {table}"


def test_rls_write_isolation(two_users):
    """AC3: user B cannot write into user A's rows (or forge user_id)."""
    (_a, user_a), (client_b, user_b) = two_users
    with pytest.raises(Exception):
        client_b.table("identities").insert({
            "user_id": user_a, "kind": "specialist", "name": "Evil", "slug": "evil",
        }).execute()
    # B's own write succeeds and is stamped with B's id.
    res = client_b.table("identities").insert({
        "user_id": user_b, "kind": "specialist", "name": "B hobby",
        "slug": f"bhobby-{uuid.uuid4().hex[:6]}",
    }).execute()
    assert res.data[0]["user_id"] == user_b


def test_anonymous_writes_rejected(isolated_settings):
    """AC6: unauthenticated clients can neither read nor write user data."""
    from supabase import create_client

    anon = create_client(os.environ["MEDOT_TEST_SUPABASE_URL"], os.environ["MEDOT_TEST_SUPABASE_KEY"])
    res = anon.table("identities").select("*").execute()
    assert res.data == []
    with pytest.raises(Exception):
        anon.table("identities").insert({
            "user_id": str(uuid.uuid4()), "kind": "specialist", "name": "X", "slug": "x",
        }).execute()


def test_dynamic_domain_records_no_ddl(two_users):
    """Gardening identity + record needs zero schema changes (OD-4 proof)."""
    (client_a, user_a), _ = two_users
    domain = (client_a.table("knowledge_domains").insert({
        "user_id": user_a, "slug": f"gardening-{uuid.uuid4().hex[:6]}", "title": "Gardening",
    }).execute()).data[0]
    (client_a.table("identities").insert({
        "user_id": user_a, "kind": "specialist", "name": "Gardening",
        "slug": "gardening", "domain_id": domain["id"],
    }).execute()).data[0]
    record = (client_a.table("domain_records").insert({
        "user_id": user_a, "domain_id": domain["id"], "type_key": "gardening.plant",
        "data": {"species": "Monstera", "location": "living room", "watering_days": ["Mon", "Thu"]},
        "occurred_at": "2026-10-31T10:00:00Z",
    }).execute()).data[0]
    assert record["type_key"] == "gardening.plant"

    # Schema validation rejects a payload violating gardening.plant.
    with pytest.raises(Exception):
        client_a.table("domain_records").insert({
            "user_id": user_a, "domain_id": domain["id"], "type_key": "gardening.plant",
            "data": {"location": "no species field"},  # required field missing
            "occurred_at": "2026-10-31T10:00:00Z",
        }).execute()


def test_builtin_schemas_readable_by_all(two_users):
    (_client_a, _), (client_b, _) = two_users
    schemas = (client_b.table("domain_schemas").select("type_key")
               .is_("user_id", "null").execute()).data
    keys = {s["type_key"] for s in schemas}
    assert "gardening.plant" in keys and "health.meal" in keys
