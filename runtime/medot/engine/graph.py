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


def _tool_schema(tool: Any) -> dict:
    """OpenAI function schema for either a Medot ToolDef or a LangChain tool
    (MCP connectors arrive as StructuredTools)."""
    args_model = getattr(tool, "args_model", None) or getattr(tool, "args_schema", None)
    if hasattr(args_model, "model_json_schema"):
        schema = args_model.model_json_schema()
        schema.pop("title", None)
        schema.pop("additionalProperties", None)
    else:
        schema = {"type": "object", "properties": {}}
    description = getattr(tool, "description", "") or tool.name
    return {
        "type": "function",
        "function": {"name": tool.name, "description": description[:1000], "parameters": schema},
    }


class AgentGraphs:
    """Compiled-turn factory: model + granted tools + system prompt."""

    def __init__(self, model: Any, tools: list, system_prompt: str, checkpointer: Any = None):
        self.model = model
        registry_tools = [t for t in tools if isinstance(t, ToolDef)]
        self.tools = {t.name: t for t in registry_tools}
        self.langchain_tools = {t.name: t for t in tools if not isinstance(t, ToolDef)}
        self.system_prompt = system_prompt
        self.checkpointer = checkpointer
        self._compiled = None

    def compile(self):
        if self._compiled is not None:
            return self._compiled

        model = self.model
        tool_defs = self.tools
        lc_tools = self.langchain_tools
        tool_schemas = [_tool_schema(t) for t in [*tool_defs.values(), *lc_tools.values()]]
        system_prompt = self.system_prompt

        async def agent_node(state: AgentState) -> dict:
            bound = model.bind_tools(tool_schemas) if tool_schemas else model
            result = await bound.ainvoke([{"role": "system", "content": system_prompt}, *state["messages"]])
            return {"messages": [result]}

        async def tools_node(state: AgentState) -> dict:
            last = state["messages"][-1]
            results: list[ToolMessage] = []
            for call in last.tool_calls or []:
                args = call.get("args") or {}
                tool = tool_defs.get(call["name"])
                if tool is not None:
                    if tool.requires_approval:
                        decision = interrupt({"tool": tool.name, "args": args, "proposal": tool.proposal(args)})
                        if not decision or not decision.get("approved"):
                            results.append(ToolMessage(content="denied by the user", tool_call_id=call["id"]))
                            continue
                    try:
                        outcome = await tool.handler(_CLIENT["client"], _CLIENT["user_id"], **dict(args))
                        content = json.dumps(outcome, default=str)
                    except Exception as exc:  # noqa: BLE001 - tool errors reach the model, not the log only
                        content = f"error: {exc}"
                elif call["name"] in lc_tools:
                    try:
                        content = str(await lc_tools[call["name"]].ainvoke(dict(args)))
                    except Exception as exc:  # noqa: BLE001
                        content = f"error: {exc}"
                else:
                    content = "unknown tool"
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
