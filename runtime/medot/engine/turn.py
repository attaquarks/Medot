"""One conversation turn as a LangGraph StateGraph (doc 11 §2/§8).

`run_turn` drives the agent graph (model + granted tools + approval
interrupt) and returns either a reply or an approval interrupt for the
caller to propose to the user.
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage, SystemMessage

from .graph import AgentGraphs, bind_client_context


def seed_messages(system_prompt: str, history: list[BaseMessage]) -> list[BaseMessage]:
    """System segment first (doc 11 §7: instructions → context → conversation)."""
    return [SystemMessage(content=system_prompt), *history]


def _last_reply(messages: list[Any]) -> str:
    """The last AI message with content and no pending tool calls."""
    for message in reversed(messages):
        if (
            getattr(message, "type", "") == "ai"
            and getattr(message, "content", "")
            and not getattr(message, "tool_calls", None)
        ):
            return str(message.content)
    return ""


async def run_turn(
    model: Any,
    system_prompt: str,
    history: list[BaseMessage],
    *,
    thread_id: str,
    checkpointer: Any = None,
    tools: list | None = None,
    client: Any = None,
    user_id: str | None = None,
) -> dict:
    """Run one agent turn. Returns {"reply", "interrupt"}:
    - reply set, interrupt None → Me. answered;
    - interrupt set → an approval is required (value = proposal payload)."""
    if client is not None and user_id:
        bind_client_context(client, user_id)
    graph = AgentGraphs(model, tools or [], system_prompt, checkpointer).compile()
    config = {"configurable": {"thread_id": thread_id}}
    result = await graph.ainvoke(
        {"messages": seed_messages(system_prompt, history), "reply": ""},
        config,
    )
    messages = result.get("messages", []) if isinstance(result, dict) else []
    interrupts = (result.get("__interrupt__") or []) if isinstance(result, dict) else []
    if interrupts:
        value = getattr(interrupts[-1], "value", None)
        return {"reply": "", "interrupt": value or {}}
    return {"reply": _last_reply(messages), "interrupt": None}


async def resume_turn(
    model: Any,
    system_prompt: str,
    *,
    thread_id: str,
    checkpointer: Any = None,
    tools: list | None = None,
    client: Any = None,
    user_id: str | None = None,
    decision: dict,
) -> str:
    """Resume an interrupted turn with the user's decision; returns the reply."""
    if client is not None and user_id:
        bind_client_context(client, user_id)
    graph = AgentGraphs(model, tools or [], system_prompt, checkpointer).compile()
    config = {"configurable": {"thread_id": thread_id}}
    from langgraph.types import Command

    result = await graph.ainvoke(Command(resume=decision), config)
    messages = result.get("messages", []) if isinstance(result, dict) else []
    return _last_reply(messages)
