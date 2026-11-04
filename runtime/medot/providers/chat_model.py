"""The model layer: one chat-model instance per model profile, no env vars.

Thin `BaseChatModel` adapter over `litellm.acompletion` with **per-call**
`api_key`/`api_base` (doc 11 §5 fallback path — adopted directly because it
avoids the process-global credential problem of ChatLiteLLM* without adding
a dependency). LiteLLM stays the provider layer; LangChain stays the
interface.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import litellm
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from .discovery import litellm_target


class ProfileChatModel(BaseChatModel):
    """A chat model bound to one model profile's credentials (per-call)."""

    model_string: str
    api_key: str
    api_base: str | None = None

    @property
    def _llm_type(self) -> str:
        return "litellm-profile"

    def bind_tools(self, tools: list[dict], **_: Any) -> ProfileChatModel:
        """Bind OpenAI-format tool schemas; returns a copy carrying them."""
        return self.model_copy(update={"bound_tools": tools})

    def _convert(self, messages: list[BaseMessage]) -> list[dict[str, str]]:
        return [
            {"role": "assistant" if m.type == "ai" else "system" if m.type == "system" else "user", "content": str(m.content)}
            for m in messages
        ]

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError("ProfileChatModel is async-only; use ainvoke/ainvoke")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        response = await litellm.acompletion(
            model=self.model_string,
            api_key=self.api_key,
            api_base=self.api_base,
            messages=self._convert(messages),
            max_tokens=kwargs.pop("max_tokens", 1024),
            num_retries=0,
            tools=self.bound_tools or None,
            **kwargs,
        )
        raw = response.choices[0].message
        tool_calls = []
        for tc in getattr(raw, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except ValueError:
                args = {}
            tool_calls.append({"name": tc.function.name, "args": args, "id": tc.id, "type": "tool_call"})
        message = AIMessage(content=raw.content or "", tool_calls=tool_calls)
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        stream = await litellm.acompletion(
            model=self.model_string,
            api_key=self.api_key,
            api_base=self.api_base,
            messages=self._convert(messages),
            max_tokens=kwargs.pop("max_tokens", 1024),
            stream=True,
            num_retries=0,
            **kwargs,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield ChatGenerationChunk(message=AIMessageChunk(content=delta))


def chat_model_for_profile(provider: str, model: str, api_base: str | None, api_key: str) -> ProfileChatModel:
    """Build the model instance for one profile row + keystore credential."""
    model_string, base = litellm_target(provider, model, api_base)
    return ProfileChatModel(model_string=model_string, api_key=api_key, api_base=base)
