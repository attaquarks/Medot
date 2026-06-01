"""BaseAgent — the reasoning loop shared by both agents.

One turn:
  1. recall relevant long-term memories (pgvector) for this message
  2. assemble prompt: system + memories + short-term history + user message
  3. ask the LLM (local first, cloud fallback) with the agent's tool schemas
  4. if the model requests tools, execute them and feed results back (max N hops)
  5. persist the exchange to short-term memory; opportunistically store facts

Subclasses supply: name, system_prompt, and a populated ToolRegistry.
"""
from __future__ import annotations

import json

from ..llm.router import LLMRouter, get_router
from ..logging import get_logger
from ..memory.long_term import LongTermStore
from ..memory.short_term import ShortTermMemory, get_short_term
from .tools import ToolContext, ToolRegistry

log = get_logger("agent")
MAX_TOOL_HOPS = 4


class BaseAgent:
    name: str = "base"
    system_prompt: str = "You are a helpful assistant."

    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.llm: LLMRouter = get_router()
        self.short: ShortTermMemory = get_short_term()
        self.long = LongTermStore(self.name)

    async def handle_message(self, tenant_id: str, peer: str, text: str) -> str:
        ctx = ToolContext(tenant_id=tenant_id, agent=self.name, peer=peer)

        memories = await self.long.recall(tenant_id, text, k=5)
        history = await self.short.history(tenant_id, self.name, peer)

        messages: list[dict] = [{"role": "system", "content": self._system(memories)}]
        messages += history
        messages.append({"role": "user", "content": text})

        # Hard tasks (scheduling math, multi-step triage) can opt into cloud.
        complexity = "hard" if self._looks_hard(text) else "auto"

        for hop in range(MAX_TOOL_HOPS):
            raw = await self.llm.complete(
                messages, tools=self.registry.schemas(), complexity=complexity
            )
            calls = self._extract_tool_calls(raw)
            if not calls:
                await self._persist(tenant_id, peer, text, raw)
                return raw
            messages.append({"role": "assistant", "content": raw})
            for call in calls:
                result = await self.registry.dispatch(call["name"], call.get("arguments", {}), ctx)
                messages.append(
                    {"role": "tool", "name": call["name"], "content": json.dumps(result, default=str)}
                )
        # Ran out of hops — return a best-effort summary.
        final = await self.llm.complete(messages, complexity="auto")
        await self._persist(tenant_id, peer, text, final)
        return final

    # --- helpers -------------------------------------------------------------
    def _system(self, memories: list[str]) -> str:
        if not memories:
            return self.system_prompt
        joined = "\n".join(f"- {m}" for m in memories)
        return f"{self.system_prompt}\n\nRelevant long-term memory:\n{joined}"

    async def _persist(self, tenant_id: str, peer: str, user_text: str, reply: str) -> None:
        await self.short.append(tenant_id, self.name, peer, "user", user_text)
        await self.short.append(tenant_id, self.name, peer, "assistant", reply)

    def _looks_hard(self, text: str) -> bool:
        hard_signals = ("reschedule", "summarize", "plan", "analyze", "draft", "negotiate")
        return any(s in text.lower() for s in hard_signals)

    @staticmethod
    def _extract_tool_calls(raw: str) -> list[dict]:
        """Parse tool calls.

        LiteLLM normalises native function-calls into the message, but some local
        models emit a JSON block instead. We support a simple convention:
        a fenced ```tool {"name": "...", "arguments": {...}} ``` block.
        Native tool_calls handling is wired in the service layer; this keeps the
        loop model-agnostic for local models without function-calling.
        """
        calls: list[dict] = []
        marker = "```tool"
        if marker in raw:
            for chunk in raw.split(marker)[1:]:
                body = chunk.split("```", 1)[0].strip()
                try:
                    calls.append(json.loads(body))
                except json.JSONDecodeError:
                    continue
        return calls
