"""KnowledgeService (M3): plain-language reads over the knowledge tables."""
from test_whatsapp_manager import FakeClient

from medot.knowledge import service


def _world(client):
    client.tables["knowledge_domains"] = [
        {"id": "dom-g", "user_id": "u1", "slug": "global", "title": "Everything", "summary": "", "owner_identity_id": None},
        {"id": "dom-h", "user_id": "u1", "slug": "health", "title": "Health", "summary": "Body stuff", "owner_identity_id": None},
    ]
    client.tables["knowledge_nodes"] = [
        {"id": "n1", "user_id": "u1", "domain_id": "dom-g", "name": "Priya", "summary": "sister", "node_type": "entity"},
        {"id": "n2", "user_id": "u1", "domain_id": "dom-h", "name": "Weight", "summary": "", "node_type": "entity"},
    ]
    client.tables["knowledge_edges"] = [
        {"id": "e1", "user_id": "u1", "domain_id": "dom-g", "fact": "Priya is allergic to peanuts",
         "relation": "is allergic to", "valid_from": "2026-11-01T10:00:00+00:00", "valid_to": None},
        {"id": "e2", "user_id": "u1", "domain_id": "dom-h", "fact": "Weight was 74.2 kg",
         "relation": "weighed", "valid_from": "2026-11-05T08:00:00+00:00", "valid_to": None},
    ]


def test_overview_counts_per_domain():
    client = FakeClient()
    _world(client)
    client.tables["memory_episodes"] = [{"id": "ep1", "user_id": "u1"}, {"id": "ep2", "user_id": "u1"}]
    out = service.overview(client, "u1")
    assert out["episodes_total"] == 2
    by_slug = {d["slug"]: d for d in out["domains"]}
    assert by_slug["global"]["facts"] == 1 and by_slug["global"]["topics"] == 1
    assert by_slug["health"]["facts"] == 1 and by_slug["health"]["topics"] == 1
    assert by_slug["health"]["latest_fact_at"] == "2026-11-05T08:00:00+00:00"


def test_domain_detail_returns_topics_and_facts():
    client = FakeClient()
    _world(client)
    detail = service.domain_detail(client, "u1", "dom-g")
    assert detail["domain"]["title"] == "Everything"
    assert [t["name"] for t in detail["topics"]] == ["Priya"]
    assert detail["facts"][0]["fact"] == "Priya is allergic to peanuts"


def test_domain_detail_none_for_foreign_or_missing():
    client = FakeClient()
    _world(client)
    assert service.domain_detail(client, "u1", "nope") is None
    assert service.domain_detail(client, "u2", "dom-g") is None


def test_records_join_schema_titles():
    client = FakeClient()
    _world(client)
    client.tables["domain_schemas"] = [
        {"type_key": "health.weight_measurement", "title": "Weight measurement", "user_id": None},
    ]
    client.tables["domain_records"] = [
        {"id": "r1", "user_id": "u1", "domain_id": "dom-h", "type_key": "health.weight_measurement",
         "data": {"weight_kg": 74.2}, "occurred_at": "2026-11-05T08:00:00+00:00"},
    ]
    out = service.records(client, "u1", "dom-h")
    assert out["records"][0]["type_title"] == "Weight measurement"
    assert out["records"][0]["data"] == {"weight_kg": 74.2}
    assert service.records(client, "u1", "dom-g")["records"] == []
