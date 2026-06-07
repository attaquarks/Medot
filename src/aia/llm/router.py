"""Hybrid LLM router.

Policy:
  * DEFAULT  -> local model (Ollama). Private, free, good enough for routine work.
  * FALLBACK -> cloud model (OpenAI / Anthropic) when:
        - the caller asks for it (`complexity="hard"`), or
        - LLM_FORCE_CLOUD=1, or
        - the local call errors / times out.
  * If no cloud key is configured the system stays 100% offline and simply
    retries locally.

All callers go through `get_router()` so the policy lives in exactly one place.
LiteLLM gives us a single API across Ollama, OpenAI and Anthropic.
"""
from __future__ import annotations

from functools import lru_cache
import json
from typing import Any, Literal

import litellm
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import get_settings
from ..logging import get_logger

log = get_logger("llm")
Complexity = Literal["auto", "routine", "hard"]


class LLMRouter:
    def __init__(self) -> None:
        s = get_settings()
        self.local = s.llm_local_model
        self.cloud = s.llm_cloud_model
        self.embedding_model = s.llm_embedding_model
        self.force_cloud = s.llm_force_cloud
        self.has_cloud = bool(s.openai_api_key or s.anthropic_api_key)
        # Point LiteLLM at the local Ollama server.
        litellm.api_base = s.ollama_base_url if self.local.startswith("ollama/") else None

    def _pick(self, complexity: Complexity) -> str:
        if (self.force_cloud or complexity == "hard") and self.has_cloud:
            return self.cloud
        return self.local

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, max=4))
    async def _call(self, model: str, messages: list[dict], **kw: Any) -> str:
        kwargs: dict[str, Any] = {"model": model, "messages": messages, **kw}
        if model.startswith("ollama/"):
            kwargs["api_base"] = get_settings().ollama_base_url
        resp = await litellm.acompletion(**kwargs)
        message = resp["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            blocks: list[str] = []
            for call in tool_calls:
                fn = call.get("function", {})
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                blocks.append(
                    "```tool\n"
                    + json.dumps({"name": fn.get("name"), "arguments": args})
                    + "\n```"
                )
            return "\n".join(blocks)
        return message.get("content") or ""

    async def complete(
        self,
        messages: list[dict],
        *,
        complexity: Complexity = "auto",
        temperature: float = 0.3,
        tools: list[dict] | None = None,
    ) -> str:
        """Return assistant text, transparently falling back local -> cloud."""
        model = self._pick(complexity)
        try:
            return await self._call(
                model, messages, temperature=temperature, tools=tools
            )
        except Exception as exc:  # local failed — try cloud if we can
            log.warning("llm_primary_failed", model=model, error=str(exc))
            if model != self.cloud and self.has_cloud:
                log.info("llm_fallback_cloud", model=self.cloud)
                return await self._call(
                    self.cloud, messages, temperature=temperature, tools=tools
                )
            raise

    async def embed(self, text: str) -> list[float]:
        kwargs: dict[str, Any] = {"model": self.embedding_model, "input": text}
        if self.embedding_model.startswith("ollama/"):
            kwargs["api_base"] = get_settings().ollama_base_url
        resp = await litellm.aembedding(**kwargs)
        return resp["data"][0]["embedding"]


@lru_cache
def get_router() -> LLMRouter:
    return LLMRouter()
