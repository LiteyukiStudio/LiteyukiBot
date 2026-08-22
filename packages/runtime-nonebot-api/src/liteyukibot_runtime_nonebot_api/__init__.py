"""Typed, NoneBot-independent runtime API facade."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from liteyukibot.events import ConversationRef, JsonValue, Message
from liteyukibot.runtime_api import (
    BotSnapshot,
    EventSnapshot,
    RuntimeApiBackend,
    RuntimeApiError,
    RuntimeBinding,
    RuntimeCallContext,
    RuntimeNamespaceProxy,
    SendResult,
)

NoneBotEventSnapshot = EventSnapshot
NoneBotBotSnapshot = BotSnapshot


class NoneBotEventProxy(RuntimeNamespaceProxy):
    """Typed facade for the portable NoneBot event contract."""

    async def snapshot(self) -> NoneBotEventSnapshot:
        value = await self.call("snapshot")
        if not isinstance(value, Mapping):
            raise RuntimeApiError(self.binding.runtime, self.binding.api, "snapshot", "RUNTIME_API_INVALID_RESULT")
        try:
            return NoneBotEventSnapshot.model_validate(value)
        except ValueError as error:
            raise RuntimeApiError(
                self.binding.runtime,
                self.binding.api,
                "snapshot",
                "RUNTIME_API_INVALID_RESULT",
            ) from error

    async def send(self, message: str | Message) -> SendResult:
        argument: JsonValue = message if isinstance(message, str) else cast(
            dict[str, JsonValue], message.model_dump(mode="json")
        )
        value = await self.call("send", {"message": argument})
        return _send_result(self, "send", value)


class NoneBotBotProxy(RuntimeNamespaceProxy):
    """Typed facade for exact-bot identity and portable proactive sending."""

    async def snapshot(self) -> NoneBotBotSnapshot:
        value = await self.call("snapshot")
        if not isinstance(value, Mapping):
            raise RuntimeApiError(self.binding.runtime, self.binding.api, "snapshot", "RUNTIME_API_INVALID_RESULT")
        try:
            return NoneBotBotSnapshot.model_validate(value)
        except ValueError as error:
            raise RuntimeApiError(
                self.binding.runtime,
                self.binding.api,
                "snapshot",
                "RUNTIME_API_INVALID_RESULT",
            ) from error

    async def send(self, message: Message, conversation: ConversationRef) -> SendResult:
        arguments = cast(
            Mapping[str, JsonValue],
            {
                "message": cast(dict[str, JsonValue], message.model_dump(mode="json")),
                "conversation": cast(dict[str, JsonValue], conversation.model_dump(mode="json")),
            },
        )
        value = await self.call("send", arguments)
        return _send_result(self, "send", value)


def event_proxy_factory(
    *,
    binding: RuntimeBinding,
    backend: RuntimeApiBackend | None,
    context: RuntimeCallContext | None,
    reason: str = "unavailable",
) -> NoneBotEventProxy:
    return NoneBotEventProxy(binding, backend, context, reason=reason)


def bot_proxy_factory(
    *,
    binding: RuntimeBinding,
    backend: RuntimeApiBackend | None,
    context: RuntimeCallContext | None,
    reason: str = "unavailable",
) -> NoneBotBotProxy:
    return NoneBotBotProxy(binding, backend, context, reason=reason)


def _send_result(proxy: RuntimeNamespaceProxy, operation: str, value: JsonValue) -> SendResult:
    if not isinstance(value, Mapping):
        raise RuntimeApiError(proxy.binding.runtime, proxy.binding.api, operation, "RUNTIME_API_INVALID_RESULT")
    try:
        return SendResult.model_validate(value)
    except ValueError as error:
        raise RuntimeApiError(
            proxy.binding.runtime,
            proxy.binding.api,
            operation,
            "RUNTIME_API_INVALID_RESULT",
        ) from error


__all__ = [
    "NoneBotBotProxy",
    "NoneBotBotSnapshot",
    "NoneBotEventProxy",
    "NoneBotEventSnapshot",
    "SendResult",
    "bot_proxy_factory",
    "event_proxy_factory",
]
