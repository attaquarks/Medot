"""One conversation turn as a LangGraph StateGraph (doc 11 §2).

route → respond → (post-turn persistence happens outside the graph; the
memory-enqueue node arrives with M3a). The checkpointer persists execution
state per thread_id = "u:{user}:c:{conversation}:r:{run}".
"""
from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class TurnState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    reply: str


def build_turn_graph(model: BaseChatModel, system_prompt: str, checkpointer=None):
    """Compile the turn graph for one identity + model profile."""

    async def respond(state: TurnState) -> dict:
        result = await model.ainvoke(state["messages"])
        return {"reply": str(result.content)}

    graph = StateGraph(TurnState)
    graph.add_node("respond", respond)
    graph.add_edge(START, "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer or MemorySaver())


def seed_messages(system_prompt: str, history: list[BaseMessage]) -> list[BaseMessage]:
    """System segment first (doc 11 §7: instructions → context → conversation)."""
    return [SystemMessage(content=system_prompt), *history]


async def run_turn(
    model: BaseChatModel,
    system_prompt: str,
    history: list[BaseMessage],
    *,
    thread_id: str,
    checkpointer=None,
) -> str:
    """Run one turn; returns Me.'s reply text."""
    graph = build_turn_graph(model, system_prompt, checkpointer)
    config = {"configurable": {"thread_id": thread_id}}
    result = await graph.ainvoke(
        {"messages": seed_messages(system_prompt, history), "reply": ""},
        config,
    )
    return result["reply"]
