"""Tool abstraction shared by both agents.

A Tool is a name + JSON-schema parameter spec + an async handler. The registry
renders the OpenAI-compatible `tools` array for the LLM and dispatches calls.
Each agent owns its own registry, so their tool sets never overlap (Requirement #1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

ToolFn = Callable[..., Awaitable[Any]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema for the arguments object
    handler: ToolFn

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def tool(self, name: str, description: str, parameters: dict) -> Callable[[ToolFn], ToolFn]:
        """Decorator form:  @registry.tool("name", "desc", {schema})"""
        def deco(fn: ToolFn) -> ToolFn:
            self.register(Tool(name, description, parameters, fn))
            return fn
        return deco

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    async def dispatch(self, name: str, arguments: dict, ctx: "ToolContext") -> Any:
        if name not in self._tools:
            return {"error": f"unknown tool '{name}'"}
        return await self._tools[name].handler(ctx=ctx, **arguments)


@dataclass
class ToolContext:
    """Everything a tool handler needs to act on behalf of one tenant."""
    tenant_id: str
    agent: str
    peer: str  # the WhatsApp id we're talking to
