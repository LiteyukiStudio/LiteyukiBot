"""Typed, AstrBot-independent Alpha10.1 runtime API facade."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from liteyukibot.events import ConversationRef, JsonValue, Message, Segment
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


class AstrBotEventSnapshot(EventSnapshot):
    """Canonical snapshot with Alpha9 AstrBot field compatibility properties."""

    @property
    def platform_id(self) -> str:
        return _extension_text(self, "platform_id")

    @property
    def platform_name(self) -> str:
        return _extension_text(self, "platform_name")

    @property
    def session_id(self) -> str:
        return _extension_text(self, "session_id")

    @property
    def group_id(self) -> str | None:
        return self.conversation.id if self.conversation.type == "group" else None

    @property
    def sender_id(self) -> str | None:
        return None if self.actor is None else self.actor.id

    @property
    def message_text(self) -> str:
        return "" if self.message is None else self.message.plain_text

    @property
    def message_type(self) -> str:
        return _extension_text(self, "message_type")

    @property
    def conversation_id(self) -> str:
        return self.conversation.id

    @property
    def conversation_type(self) -> str:
        return self.conversation.type

    @property
    def actor_name(self) -> str | None:
        return None if self.actor is None else self.actor.display_name

    @property
    def actor_is_bot(self) -> bool:
        return False if self.actor is None else self.actor.is_bot

    @property
    def message_segments(self) -> tuple[Segment, ...]:
        return () if self.message is None else self.message.segments


class AstrBotBotSnapshot(BotSnapshot):
    """Canonical bot snapshot with Alpha9 AstrBot field compatibility properties."""

    @property
    def platform_id(self) -> str:
        return _extension_text(self, "platform_id")

    @property
    def platform_name(self) -> str:
        return _extension_text(self, "platform_name")


class AstrBotEventProxy(RuntimeNamespaceProxy):
    """Typed facade for the portable AstrBot event contract."""

    async def snapshot(self) -> AstrBotEventSnapshot:
        value = await self.call("snapshot")
        if not isinstance(value, Mapping):
            raise RuntimeApiError(self.binding.runtime, self.binding.api, "snapshot", "RUNTIME_API_INVALID_RESULT")
        try:
            return AstrBotEventSnapshot.model_validate(value)
        except ValueError as error:
            raise RuntimeApiError(
                self.binding.runtime,
                self.binding.api,
                "snapshot",
                "RUNTIME_API_INVALID_RESULT",
            ) from error

    async def send(self, message: str | Message) -> SendResult:
        return await self._send(message)

    async def send_message(self, message: Message) -> SendResult:
        return await self._send(message)

    async def _send(self, message: str | Message) -> SendResult:
        argument: JsonValue = message if isinstance(message, str) else cast(
            dict[str, JsonValue], message.model_dump(mode="json")
        )
        value = await self.call("send", {"message": argument})
        return _send_result(self, "send", value)


class AstrBotBotProxy(RuntimeNamespaceProxy):
    """Typed facade for exact-bot identity and portable proactive sending."""

    async def snapshot(self) -> AstrBotBotSnapshot:
        value = await self.call("snapshot")
        if not isinstance(value, Mapping):
            raise RuntimeApiError(self.binding.runtime, self.binding.api, "snapshot", "RUNTIME_API_INVALID_RESULT")
        try:
            return AstrBotBotSnapshot.model_validate(value)
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


def proxy_factory(
    *,
    binding: RuntimeBinding,
    backend: RuntimeApiBackend | None,
    context: RuntimeCallContext | None,
    reason: str = "unavailable",
) -> AstrBotEventProxy:
    return AstrBotEventProxy(binding, backend, context, reason=reason)


def bot_proxy_factory(
    *,
    binding: RuntimeBinding,
    backend: RuntimeApiBackend | None,
    context: RuntimeCallContext | None,
    reason: str = "unavailable",
) -> AstrBotBotProxy:
    return AstrBotBotProxy(binding, backend, context, reason=reason)


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


def _extension_text(snapshot: EventSnapshot | BotSnapshot, key: str) -> str:
    values = snapshot.extensions.get("astrbot")
    if not isinstance(values, Mapping):
        return ""
    value = values.get(key)
    return value if isinstance(value, str) else ""


__all__ = [
    "AstrBotBotProxy",
    "AstrBotBotSnapshot",
    "AstrBotEventProxy",
    "AstrBotEventSnapshot",
    "SendResult",
    "bot_proxy_factory",
    "proxy_factory",
]
