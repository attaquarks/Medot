"""Engine (M4b): agent graph, approval interrupt/resume, inbound wiring."""
from typing import ClassVar

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel
from test_whatsapp_manager import FakeClient

from medot.engine import wiring
from medot.engine.turn import run_turn, seed_messages
from medot.tools.registry import ToolDef, granted_tools
from medot.whatsapp.manager import Envelope


# ---------------------------------------------------------------------------
# stub model: records prompts; optional tool_call (optionally keyed to text)
# ---------------------------------------------------------------------------
class StubChatModel(BaseChatModel):
    reply: str = "Hello from Me."
    tool_call: dict | None = None
    seen: ClassVar[list] = []

    @property
    def _llm_type(self) -> str:
        return "stub"

    def bind_tools(self, tools, **_):
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop=None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs,
    ) -> ChatResult:
        StubChatModel.seen.append(list(messages))
        # emit the tool call until a ToolMessage exists (i.e. the tool ran or was denied)
        if self.tool_call and not any(m.type == "tool" for m in messages):
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[self.tool_call]))]
            )
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.reply))])


def _envelope(text: str, peer: str = "user:509") -> Envelope:
    return Envelope(
        transport="agent_platform", message_id=f"wamid.{abs(hash(text)) % 99999}", peer=peer, chat=peer,
        sender=peer, text=text,
    )


def _me_world(client):
    """identity + instructions + chat profile."""
    client.tables.setdefault("identities", []).append({"id": "me-1", "slug": "me"})
    client.tables.setdefault("identity_instructions", []).append(
        {"identity_id": "me-1", "version": 1, "is_active": True, "content_md": "You are Me. Be kind."}
    )
    client.tables.setdefault("model_profiles", []).append(
        {"id": "prof-1", "purpose": "chat", "provider": "openai_compatible", "model": "gpt-x", "api_base": None}
    )
    client.tables.setdefault("knowledge_domains", []).append({"id": "dom-1", "slug": "global"})


class _Keystore:
    def get_secret(self, account):
        return "sk-test" if "prof-1" in account else None


_savers = {}


async def _fake_saver(user_id):
    """Mirror the real _saver_for: one saver per user, cached across calls."""
    if user_id not in _savers:
        from langgraph.checkpoint.memory import MemorySaver

        _savers[user_id] = MemorySaver()
    return _savers[user_id]


# ---------------------------------------------------------------------------
# turn graph (plain reply + history)
# ---------------------------------------------------------------------------
async def test_run_turn_returns_reply_and_seeds_system_first():
    model = StubChatModel(reply="hi there")
    result = await run_turn(model, "You are Me.", [], thread_id="t1")
    assert result == {"reply": "hi there", "interrupt": None}
    assert StubChatModel.seen[-1][0].content == "You are Me."


async def test_run_turn_passes_history_after_system():
    model = StubChatModel()
    await run_turn(model, "SYS", [HumanMessage(content="earlier")], thread_id="t2")
    seen = StubChatModel.seen[-1]
    assert seen[0].content == "SYS"
    assert "earlier" in [m.content for m in seen[1:]]


def test_seed_messages_order():
    seeded = seed_messages("SYS", [HumanMessage(content="q")])
    assert seeded[0].content == "SYS" and seeded[1].content == "q"


# ---------------------------------------------------------------------------
# the approval loop: interrupt → proposal → YES executes once, NO denies
# ---------------------------------------------------------------------------
class _ForgetArgs(BaseModel):
    match: str


def _forget_tool(executed: list) -> ToolDef:
    async def handler(client, user_id, match):
        executed.append(match)
        return {"forgotten": 1}

    return ToolDef(
        key="knowledge.forget", name="forget_fact", description="destructive",
        args_model=_ForgetArgs, requires_approval=True, handler=handler,
    )


async def test_run_turn_interrupts_for_approval_tool():
    executed = []
    forget = _forget_tool(executed)
    model = StubChatModel(
        tool_call={"name": "forget_fact", "args": {"match": "diary"}, "id": "c1", "type": "tool_call"}
    )
    result = await run_turn(model, "SYS", [], thread_id="t3", tools=[forget], client=FakeClient(), user_id="u1")
    assert result["interrupt"]["tool"] == "forget_fact"
    assert result["interrupt"]["args"] == {"match": "diary"}
    assert executed == []  # the tool did NOT run before approval


async def test_resume_approved_executes_tool_exactly_once():
    executed = []
    forget = _forget_tool(executed)
    from langgraph.checkpoint.memory import MemorySaver

    saver = MemorySaver()
    model = StubChatModel(
        reply="Forgotten.",
        tool_call={"name": "forget_fact", "args": {"match": "diary"}, "id": "c1", "type": "tool_call"},
    )
    interrupted = await run_turn(
        model, "SYS", [], thread_id="t4", checkpointer=saver, tools=[forget], client=FakeClient(), user_id="u1"
    )
    assert interrupted["interrupt"] is not None
    reply = await wiring.resume_turn(
        model, "SYS", thread_id="t4", checkpointer=saver, tools=[forget],
        client=FakeClient(), user_id="u1", decision={"approved": True},
    )
    assert reply == "Forgotten."
    assert executed == ["diary"]  # exactly once


async def test_resume_denied_never_executes_tool():
    executed = []
    forget = _forget_tool(executed)
    from langgraph.checkpoint.memory import MemorySaver

    saver = MemorySaver()
    model = StubChatModel(
        reply="Kept everything.",
        tool_call={"name": "forget_fact", "args": {"match": "diary"}, "id": "c1", "type": "tool_call"},
    )
    await run_turn(
        model, "SYS", [], thread_id="t5", checkpointer=saver, tools=[forget], client=FakeClient(), user_id="u1"
    )
    reply = await wiring.resume_turn(
        model, "SYS", thread_id="t5", checkpointer=saver, tools=[forget],
        client=FakeClient(), user_id="u1", decision={"approved": False},
    )
    assert executed == []
    assert reply == "Kept everything."


# ---------------------------------------------------------------------------
# registry grants
# ---------------------------------------------------------------------------
def test_granted_tools_auto_seeds_me():
    client = FakeClient()
    client.tables.setdefault("identities", []).append({"id": "me-1", "slug": "me"})
    tools = granted_tools(client, "u1", "me-1")
    assert {t.key for t in tools} == {"knowledge.recall", "knowledge.remember", "knowledge.forget"}
    grants = client.tables["identity_tool_grants"]
    forget_grant = next(g for g in grants if g["tool_key"] == "knowledge.forget")
    assert forget_grant["requires_approval"] is True


def test_grants_are_read_not_reseeded_when_present():
    client = FakeClient()
    client.tables.setdefault("identities", []).append({"id": "me-1", "slug": "me"})
    client.tables.setdefault("identity_tool_grants", []).append({"identity_id": "me-1", "tool_key": "knowledge.recall"})
    tools = granted_tools(client, "u1", "me-1")
    assert [t.key for t in tools] == ["knowledge.recall"]
    assert len(client.tables["identity_tool_grants"]) == 1


# ---------------------------------------------------------------------------
# wiring helpers
# ---------------------------------------------------------------------------
def test_me_instructions_reads_active_version():
    client = FakeClient()
    assert "personal companion" in wiring.me_instructions(client, "u1")
    _me_world(client)
    assert wiring.me_instructions(client, "u1") == "You are Me. Be kind."


def test_resolve_chat_model_without_profile_gives_notice():
    model, notice = wiring.resolve_chat_model(FakeClient(), "u1")
    assert model is None
    assert "AI Providers" in notice


def test_load_history_orders_messages():
    client = FakeClient()
    _me_world(client)
    client.tables.setdefault("conversations", []).append({"id": "conv-1", "channel": "whatsapp", "peer": "u:509"})
    client.tables["messages"] = [
        {"conversation_id": "conv-1", "direction": "inbound", "body": "second", "occurred_at": "2026-11-01T10:02:00Z"},
        {"conversation_id": "conv-1", "direction": "outbound", "body": "reply", "occurred_at": "2026-11-01T10:01:00Z"},
        {"conversation_id": "conv-1", "direction": "inbound", "body": "first", "occurred_at": "2026-11-01T10:00:00Z"},
    ]
    history = wiring.load_history(client, "u1", "u:509")
    assert [m.content for m in history] == ["first", "reply", "second"]
    assert isinstance(history[1], wiring.AIMessage)


def test_parse_decision():
    assert wiring.parse_decision("YES") is True
    assert wiring.parse_decision("no.") is False
    assert wiring.parse_decision("what?") is None


# ---------------------------------------------------------------------------
# the full inbound flow with the approval loop (real graph, fake LLM)
# ---------------------------------------------------------------------------
class _Manager:
    def __init__(self):
        self.sent = []

    async def send(self, text, transport_name=None, to=None):
        self.sent.append((text, transport_name, to))


@pytest.fixture()
def manager(monkeypatch):
    import medot.whatsapp.manager as wa_manager

    m = _Manager()
    monkeypatch.setattr(wa_manager, "get_manager", lambda: m)
    return m


@pytest.fixture()
def keystore(monkeypatch):
    monkeypatch.setattr(wiring, "get_keystore", lambda: _Keystore())


async def test_handle_inbound_full_approval_loop(monkeypatch, manager, keystore):
    """forget proposal → YES → fact deleted → confirmed."""
    client = FakeClient()
    _me_world(client)
    client.tables.setdefault("conversations", []).append(
        {"id": "conv-1", "channel": "whatsapp", "peer": "user:509"}
    )
    client.tables.setdefault("knowledge_edges", []).append({"id": "edge-1", "user_id": "u1", "fact": "diary secret"})
    monkeypatch.setattr(
        wiring, "chat_model_for_profile",
        lambda *a: StubChatModel(
            reply="Done — forgot it.",
            tool_call={"name": "forget_fact", "args": {"match": "diary"}, "id": "c1", "type": "tool_call"}
        ),
    )
    monkeypatch.setattr(wiring, "_saver_for", _fake_saver)

    await wiring.handle_inbound(client, "u1", _envelope("please forget my diary secret"))
    proposals = [t for t, _, _ in manager.sent if "YES" in t]
    assert proposals, "a proposal must be sent"
    approvals = client.tables["approvals"]
    assert approvals[0]["status"] == "pending"
    assert approvals[0]["payload"]["peer"] == "user:509"

    await wiring.handle_inbound(client, "u1", _envelope("YES"))
    assert any("forgot" in t.lower() for t, _, _ in manager.sent), manager.sent
    assert approvals[0]["status"] == "approved"
    assert client.tables["knowledge_edges"] == []  # the fact is gone
    runs = client.tables["agent_runs"]
    # the interrupted run is created awaiting_approval, then closes as succeeded
    assert approvals[0]["run_id"] in {r["id"] for r in runs}
    assert any(r["status"] == "succeeded" for r in runs)


async def test_handle_inbound_denial_keeps_facts(monkeypatch, manager, keystore):
    client = FakeClient()
    _me_world(client)
    client.tables.setdefault("knowledge_edges", []).append({"id": "edge-1", "user_id": "u1", "fact": "diary secret"})
    monkeypatch.setattr(
        wiring, "chat_model_for_profile",
        lambda *a: StubChatModel(
            reply="Kept everything.",
            tool_call={"name": "forget_fact", "args": {"match": "diary"}, "id": "c1", "type": "tool_call"}
        ),
    )
    monkeypatch.setattr(wiring, "_saver_for", _fake_saver)

    await wiring.handle_inbound(client, "u1", _envelope("forget my diary"))
    await wiring.handle_inbound(client, "u1", _envelope("NO"))
    assert client.tables["approvals"][0]["status"] == "denied"
    assert client.tables["knowledge_edges"] != []  # nothing deleted


async def test_handle_inbound_non_decision_prompts_again(monkeypatch, manager, keystore):
    client = FakeClient()
    _me_world(client)
    monkeypatch.setattr(
        wiring, "chat_model_for_profile",
        lambda *a: StubChatModel(
            reply="x",
            tool_call={"name": "forget_fact", "args": {"match": "d"}, "id": "c1", "type": "tool_call"}
        ),
    )
    monkeypatch.setattr(wiring, "_saver_for", _fake_saver)
    await wiring.handle_inbound(client, "u1", _envelope("forget d"))
    after_proposal = len(manager.sent)
    await wiring.handle_inbound(client, "u1", _envelope("maybe later"))
    assert any("YES" in t for t, _, _ in manager.sent[after_proposal:])


async def test_handle_inbound_without_profile_notifies_once(monkeypatch, manager):
    await wiring.handle_inbound(FakeClient(), "u1", _envelope("hi"))
    await wiring.handle_inbound(FakeClient(), "u1", _envelope("hi again"))
    assert manager.sent.count((wiring.NO_MODEL_REPLY, "agent_platform", "user:509")) == 1


async def test_handle_inbound_retrieves_knowledge_into_prompt(monkeypatch, manager, keystore):
    """M3b: remembered facts about the message's topic reach the model prompt."""
    client = FakeClient()
    _me_world(client)
    client.tables["knowledge_edges"] = [
        {"user_id": "u1", "fact": "Priya is allergic to peanuts"},
    ]
    captured = {}

    async def fake_run_turn(model, system_prompt, history, **kw):
        captured["system"] = system_prompt
        return {"reply": "Got it.", "interrupt": None}

    monkeypatch.setattr(wiring, "run_turn", fake_run_turn)
    monkeypatch.setattr(wiring, "_saver_for", _fake_saver)

    await wiring.handle_inbound(client, "u1", _envelope("what can I cook for Priya?"))
    assert "What you remember that may be relevant here:" in captured["system"]
    assert "Priya is allergic to peanuts" in captured["system"]
    assert "You are Me. Be kind." in captured["system"]


async def test_handle_inbound_skips_recall_block_when_nothing_matches(monkeypatch, manager, keystore):
    client = FakeClient()
    _me_world(client)
    captured = {}

    async def fake_run_turn(model, system_prompt, history, **kw):
        captured["system"] = system_prompt
        return {"reply": "Hi.", "interrupt": None}

    monkeypatch.setattr(wiring, "run_turn", fake_run_turn)
    monkeypatch.setattr(wiring, "_saver_for", _fake_saver)

    await wiring.handle_inbound(client, "u1", _envelope("hello there"))
    assert "What you remember" not in captured["system"]
