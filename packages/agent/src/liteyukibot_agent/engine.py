"""Model-facing adapter with a testable OpenAI-compatible boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    tool_id: str
    arguments: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ModelReply:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


class AgentEngine(Protocol):
    async def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        tools: Sequence[Mapping[str, object]] = (),
    ) -> ModelReply: ...


class OpenAIChatEngine:
    """OpenAI SDK adapter intentionally limited to the compatible chat API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None,
        model: str,
    ) -> None:
        if not api_key or not model:
            raise ValueError("agent API key and model must not be empty")
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        tools: Sequence[Mapping[str, object]] = (),
    ) -> ModelReply:
        try:
            from openai import AsyncOpenAI
        except ModuleNotFoundError as error:
            raise RuntimeError("native agent requires the openai package") from error
        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        request: dict[str, object] = {"model": self.model, "messages": list(messages)}
        if tools:
            request["tools"] = list(tools)
        completions: Any = client.chat.completions
        response = await completions.create(**request)
        message = response.choices[0].message
        calls: list[ToolCall] = []
        for call in cast(Sequence[object], message.tool_calls or ()):
            function = getattr(call, "function", None)
            if function is None:
                raise RuntimeError("model returned an unsupported custom tool call")
            name = str(function.name)
            try:
                arguments = json.loads(str(function.arguments))
            except json.JSONDecodeError as error:
                raise RuntimeError(f"model returned invalid arguments for {name!r}") from error
            if not isinstance(arguments, dict):
                raise RuntimeError(f"model returned non-object arguments for {name!r}")
            call_id = getattr(call, "id", None)
            if not isinstance(call_id, str) or not call_id:
                raise RuntimeError("model returned a tool call without an id")
            calls.append(ToolCall(id=call_id, tool_id=name, arguments=arguments))
        return ModelReply(text=message.content or "", tool_calls=tuple(calls))
