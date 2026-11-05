"""Memory (M3a): episodes + fact extraction into the knowledge graph."""
import json

from test_whatsapp_manager import FakeClient

from medot.memory import extraction as mem


def test_save_episode_inserts_row():
    client = FakeClient()
    mem.save_episode(client, "u1", "whatsapp", "I walked 5km", "Nice pace!")
    row = client.tables["memory_episodes"][0]
    assert row["kind"] == "message"
    assert "walked 5km" in row["content"] and "Nice pace!" in row["content"]
    assert row["extraction_status"] == "pending"


def test_save_facts_creates_nodes_and_edge():
    client = FakeClient()
    client.tables.setdefault("knowledge_domains", []).append({"id": "dom-1", "slug": "global"})
    saved = mem.save_facts(
        client,
        "u1",
        [mem.Fact(subject="Atta", relation="walked", object="5km", domain="health")],
    )
    assert saved == 1
    nodes = client.tables["knowledge_nodes"]
    assert {n["name"] for n in nodes} == {"Atta", "5km"}
    edge = client.tables["knowledge_edges"][0]
    assert edge["relation"] == "walked"
    assert edge["fact"] == "Atta walked 5km"


def test_save_facts_reuses_existing_nodes():
    client = FakeClient()
    client.tables.setdefault("knowledge_domains", []).append({"id": "dom-1", "slug": "global"})
    fact = mem.Fact(subject="Atta", relation="walked", object="3km")
    mem.save_facts(client, "u1", [fact])
    mem.save_facts(client, "u1", [mem.Fact(subject="Atta", relation="walked", object="7km")])
    entity_nodes = [n for n in client.tables["knowledge_nodes"] if n["node_type"] == "entity"]
    assert len(entity_nodes) == 1  # "Atta" upserted, not duplicated
    assert len(client.tables["knowledge_edges"]) == 2


def test_extraction_profile_row_present_and_absent():
    client = FakeClient()
    assert mem.extraction_profile_row(client, "u1") is None
    client.tables.setdefault("model_profiles", []).append(
        {"id": "prof-x", "purpose": "extraction", "provider": "openai_compatible", "model": "m", "api_base": None}
    )
    assert mem.extraction_profile_row(client, "u1")["id"] == "prof-x"


async def test_extract_facts_without_profile_is_zero():
    assert await mem.extract_facts(FakeClient(), "u1", "exchange") == 0


async def test_extract_facts_parses_and_saves(monkeypatch):
    client = FakeClient()
    client.tables.setdefault("knowledge_domains", []).append({"id": "dom-1", "slug": "global"})
    client.tables.setdefault("model_profiles", []).append(
        {"id": "prof-x", "purpose": "extraction", "provider": "openai_compatible", "model": "m", "api_base": None}
    )

    class _Keystore:
        def get_secret(self, account):
            return "sk-test" if "prof-x" in account else None

    monkeypatch.setattr(mem, "get_keystore", lambda: _Keystore())
    captured = {}

    async def fake_acompletion(**kw):
        captured.update(kw)
        msg = type("M", (), {"content": ""})()
        msg = type("M", (), {"content": json.dumps({"facts": [
            {"subject": "Atta", "relation": "plans to run", "object": "a marathon", "domain": "health"}
        ]})})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice]})()

    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    count = await mem.extract_facts(client, "u1", "User said: I plan to run a marathon.")
    assert count == 1
    assert captured["model"] == "openai/m"
    assert "knowledge graph" in captured["messages"][0]["content"]
    assert any(n["name"] == "a marathon" for n in client.tables["knowledge_nodes"])


async def test_extract_facts_survives_garbage(monkeypatch):
    client = FakeClient()
    client.tables.setdefault("model_profiles", []).append(
        {"id": "prof-x", "purpose": "extraction", "provider": "openai_compatible", "model": "m", "api_base": None}
    )

    class _Keystore:
        def get_secret(self, account):
            return "sk-test" if "prof-x" in account else None

    monkeypatch.setattr(mem, "get_keystore", lambda: _Keystore())

    async def fake_acompletion(**kw):
        msg = type("M", (), {"content": "I did not understand, here is prose without JSON."})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice]})()

    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    assert await mem.extract_facts(client, "u1", "exchange") == 0


def test_prompt_bounds_extraction_output():
    assert '"facts": []' in mem.EXTRACTION_PROMPT
    assert mem.EXTRACTION_MAX_TOKENS == 400


# ---------------------------------------------------------------------------
# retrieval (M3b): relevant facts pulled into the prompt before each turn
# ---------------------------------------------------------------------------
def test_keywords_picks_content_words_in_order():
    from medot.memory.retrieval import keywords

    assert keywords("What should I cook for Priya tonight?") == ["cook", "priya", "tonight"]
    assert keywords("um er hi") == []
    assert keywords("walking walking marathon") == ["walking", "marathon"]
    assert len(keywords(" ".join(f"word{i}" for i in range(30)))) == 8


def test_retrieve_knowledge_formats_matching_facts():
    from medot.memory.retrieval import retrieve_knowledge

    client = FakeClient()
    client.tables["knowledge_nodes"] = [
        {"user_id": "u1", "name": "Priya", "summary": "the user's sister"},
        {"user_id": "u2", "name": "Priya", "summary": "someone else"},  # other user, RLS
    ]
    client.tables["knowledge_edges"] = [
        {"user_id": "u1", "fact": "Priya is allergic to peanuts"},
    ]
    block = retrieve_knowledge(client, "u1", "what can I cook for Priya?")
    assert "What you remember" in block
    assert "- Priya — the user's sister" in block
    assert "- Priya is allergic to peanuts" in block
    # the other user's node is only matched when the query hits; summary line must be ours
    assert "someone else" not in block


def test_retrieve_knowledge_empty_when_nothing_matches():
    from medot.memory.retrieval import retrieve_knowledge

    client = FakeClient()
    client.tables["knowledge_nodes"] = [{"user_id": "u1", "name": "Priya", "summary": ""}]
    assert retrieve_knowledge(client, "u1", "tell me about the weather") == ""
    assert retrieve_knowledge(client, "u1", "hi") == ""
