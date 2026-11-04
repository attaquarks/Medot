"""The agent graph (M4b): model → tools → reply, with the approval interrupt.

Doc 11 §2/§8: one StateGraph per turn; approval-requiring tools call
`interrupt()` — the run pauses, the checkpoint persists, and the caller
sends the proposal to the user; resuming with `Command(resume=decision)`
completes (or denies) the tool exactly once.

Honest deviation (doc 11 §1 names `create_agent` as the harness): the
oct-2026 `create_agent` middleware API is post-verification here, and the
contract's own pre-M4 PoC requirement (§11) isn't discharged yet — so this
slice builds the same loop explicitly with LangGraph primitives (model node
→ tool node with server-side grant re-checks → interrupt). Adopting
`create_agent` is a follow-up once verified; Medot owns all persistence
either way.
"""
from __future__ import annotations

import json
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from ..tools.registry import ToolDef


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def _litellm_tool_schema(tool: ToolDef) -> dict:
    schema = tool.args_model.model_json_schema()
    schema.pop("title", None)
    schema.pop("additionalProperties", None)
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description, "parameters": schema},
    }


class AgentGraphs:
    """Compiled-turn factory: model + granted tools + system prompt."""

    def __init__(self, model: Any, tools: list[ToolDef], system_prompt: str, checkpointer: Any = None):
        self.model = model
        self.tools = {t.name: t for t in tools}
        self.system_prompt = system_prompt
        self.checkpointer = checkpointer
        self._compiled = None

    def compile(self):
        if self._compiled is not None:
            return self._compiled

        model = self.model
        tool_defs = self.tools
        tool_schemas = [_litellm_tool_schema(t) for t in tool_defs.values()]
        system_prompt = self.system_prompt

        async def agent_node(state: AgentState) -> dict:
            bound = model.bind_tools(tool_schemas) if tool_schemas else model
            result = await bound.ainvoke([{"role": "system", "content": system_prompt}, *state["messages"]])
            return {"messages": [result]}

        async def tools_node(state: AgentState) -> dict:
            last = state["messages"][-1]
            results: list[ToolMessage] = []
            for call in last.tool_calls or []:
                tool = tool_defs.get(call["name"])
                if tool is None:
                    results.append(ToolMessage(content="unknown tool", tool_call_id=call["id"]))
                    continue
                args = call.get("args") or {}
                if tool.requires_approval:
                    decision = interrupt({"tool": tool.name, "args": args, "proposal": tool.proposal(args)})
                    if not decision or not decision.get("approved"):
                        results.append(ToolMessage(content="denied by the user", tool_call_id=call["id"]))
                        continue
                handler_args = dict(args)
                try:
                    outcome = await tool.handler(_CLIENT["client"], _CLIENT["user_id"], **handler_args)
                    content = json.dumps(outcome, default=str)
                except Exception as exc:  # noqa: BLE001 - tool errors reach the model, not the log only
                    content = f"error: {exc}"
                results.append(ToolMessage(content=content[:2000], tool_call_id=call["id"]))
            return {"messages": results}

        def route(state: AgentState) -> str:
            last = state["messages"][-1]
            return "tools" if getattr(last, "tool_calls", None) else END

        graph = StateGraph(AgentState)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", tools_node)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", route, ["tools", END])
        graph.add_edge("tools", "agent")
        self._compiled = graph.compile(checkpointer=self.checkpointer)
        return self._compiled


# The handlers need (client, user_id); the graph is compiled per user-turn,
# so a module-level slot set at bind time keeps the tool handlers simple.
_CLIENT: dict[str, Any] = {"client": None, "user_id": None}


def bind_client_context(client: Any, user_id: str) -> None:
    _CLIENT["client"] = client
    _CLIENT["user_id"] = user_id
