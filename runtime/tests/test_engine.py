"""Engine (M4a): turn graph, prompt assembly, wiring — Me. actually answering."""

from typing import ClassVar

# ---------------------------------------------------------------------------
# stub model (real LangGraph runs; only the LLM is a double)
# ---------------------------------------------------------------------------
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from test_whatsapp_manager import FakeClient

from medot.engine import wiring
from medot.engine.turn import build_turn_graph, run_turn, seed_messages
from medot.whatsapp.manager import Envelope


class StubChatModel(BaseChatModel):
    """Returns a fixed reply; records the prompts it saw."""

    reply: str = "Hello from Me."
    seen: ClassVar[list] = []

    @property
    def _llm_type(self) -> str:
        return "stub"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop=None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs,
    ) -> ChatResult:
        StubChatModel.seen.append([m for m in messages])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.reply))])


# ---------------------------------------------------------------------------
# turn graph
# ---------------------------------------------------------------------------
async def test_run_turn_returns_reply_and_includes_system_first():
    model = StubChatModel(reply="hi there")
    reply = await run_turn(model, "You are Me.", [], thread_id="t1")
    assert reply == "hi there"
    graph = build_turn_graph(model, "You are Me.")
    seeded = seed_messages("You are Me.", [])
    assert seeded[0].content == "You are Me."
    assert graph is not None


async def test_run_turn_passes_history_after_system():
    model = StubChatModel()
    history = [HumanMessage(content="earlier")]
    await run_turn(model, "SYS", history, thread_id="t2")
    seen = StubChatModel.seen[-1]
    assert seen[0].content == "SYS"
    assert "earlier" in [m.content for m in seen[1:]]


# ---------------------------------------------------------------------------
# wiring helpers (fake Supabase double)
# ---------------------------------------------------------------------------
def _seed_me_identity(client):
    client.tables.setdefault("identities", []).append({"id": "me-1", "slug": "me"})
    client.tables.setdefault("identity_instructions", []).append(
        {"identity_id": "me-1", "version": 1, "is_active": True, "content_md": "You are Me. Be kind."}
    )


def test_me_instructions_reads_active_version():
    client = FakeClient()
    assert "personal companion" in wiring.me_instructions(client, "u1")  # graceful default
    _seed_me_identity(client)
    assert wiring.me_instructions(client, "u1") == "You are Me. Be kind."


def test_chat_profile_row_none_without_profiles():
    client = FakeClient()
    assert wiring.chat_profile_row(client, "u1") is None


def test_resolve_chat_model_without_profile_gives_notice():
    client = FakeClient()
    model, notice = wiring.resolve_chat_model(client, "u1")
    assert model is None
    assert "AI Providers" in notice


def test_load_history_orders_messages():
    client = FakeClient()
    _seed_me_identity(client)
    client.tables.setdefault("conversations", []).append({"id": "conv-1", "channel": "whatsapp", "peer": "u:509"})
    rows = [
        {"conversation_id": "conv-1", "direction": "inbound", "body": "first", "occurred_at": "2026-11-01T10:00:00Z"},
        {"conversation_id": "conv-1", "direction": "outbound", "body": "reply", "occurred_at": "2026-11-01T10:01:00Z"},
        {"conversation_id": "conv-1", "direction": "inbound", "body": "second", "occurred_at": "2026-11-01T10:02:00Z"},
    ]
    # the double ignores order/limit args; store pre-reversed like the DB returns
    client.tables["messages"] = list(reversed(rows))
    history = wiring.load_history(client, "u1", "u:509")
    assert [m.content for m in history] == ["first", "reply", "second"]
    assert isinstance(history[1], wiring.AIMessage)


def test_persist_outbound_inserts_message_row():
    client = FakeClient()
    wiring.persist_outbound(client, "u1", "u:509", "agent_platform", "hello!")
    assert client.tables["conversations"][0]["peer"] == "u:509"
    assert client.tables["messages"][0]["direction"] == "outbound"
    assert client.tables["messages"][0]["body"] == "hello!"


# ---------------------------------------------------------------------------
# the full inbound hook (real graph, fake LLM, fake manager.send)
# ---------------------------------------------------------------------------
async def test_handle_inbound_runs_turn_and_sends_reply(monkeypatch):
    client = FakeClient()
    _seed_me_identity(client)
    client.tables.setdefault("model_profiles", []).append(
        {"id": "prof-1", "purpose": "chat", "provider": "openai_compatible", "model": "gpt-x", "api_base": None}
    )

    class _Keystore:
        def get_secret(self, account):
            return "sk-test" if "prof-1" in account else None

    monkeypatch.setattr(wiring, "get_keystore", lambda: _Keystore())
    monkeypatch.setattr(wiring, "chat_model_for_profile", lambda *a: StubChatModel(reply="Me. here!"))

    sent = []

    class _Manager:
        async def send(self, text, transport_name=None, to=None):
            sent.append((text, transport_name, to))

    import medot.whatsapp.manager as wa_manager

    monkeypatch.setattr(wa_manager, "get_manager", lambda: _Manager())

    envelope = Envelope(
        transport="agent_platform", message_id="wamid.1", peer="user:509",
        chat="user:509", sender="user:509", text="hello",
    )
    await wiring.handle_inbound(client, "u1", envelope)
    assert sent == [("Me. here!", "agent_platform", "user:509")]
    # the exchange is persisted: outbound row from the engine
    assert any(m["direction"] == "outbound" for m in client.tables.get("messages", []))


async def test_handle_inbound_without_profile_notifies_once(monkeypatch):
    client = FakeClient()
    sent = []

    class _Manager:
        async def send(self, text, transport_name=None, to=None):
            sent.append(text)

    import medot.whatsapp.manager as wa_manager

    monkeypatch.setattr(wa_manager, "get_manager", lambda: _Manager())
    envelope = Envelope(
        transport="agent_platform", message_id="wamid.2", peer="user:1",
        chat="user:1", sender="user:1", text="hi",
    )
    await wiring.handle_inbound(client, "u1", envelope)
    await wiring.handle_inbound(client, "u1", envelope)
    assert sent.count(wiring.NO_MODEL_REPLY) == 1  # notified once, then quiet
