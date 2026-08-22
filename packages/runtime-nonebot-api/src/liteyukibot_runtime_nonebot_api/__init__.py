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
        """Return an immutable snapshot of the none bot event proxy state.

        Returns:
            The requested `NoneBotEventSnapshot` value.
        """
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
        """Send the none bot event proxy operation.

        Args:
            message: Message content associated with the operation.

        Returns:
            The `SendResult` result produced by the operation.
        """
        argument: JsonValue = message if isinstance(message, str) else cast(
            dict[str, JsonValue], message.model_dump(mode="json")
        )
        value = await self.call("send", {"message": argument})
        return _send_result(self, "send", value)


class NoneBotBotProxy(RuntimeNamespaceProxy):
    """Typed facade for exact-bot identity and portable proactive sending."""

    async def snapshot(self) -> NoneBotBotSnapshot:
        """Return an immutable snapshot of the none bot bot proxy state.

        Returns:
            The requested `NoneBotBotSnapshot` value.
        """
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
        """Send the none bot bot proxy operation.

        Args:
            message: Message content associated with the operation.
            conversation: The conversation value used by the operation.

        Returns:
            The `SendResult` result produced by the operation.
        """
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
    """Implement the event proxy factory operation for the component.

    Args:
        binding: The binding value used by the operation.
        backend: The backend value used by the operation.
        context: Runtime or authorization context for the operation.
        reason: The reason value used by the operation.

    Returns:
        The `NoneBotEventProxy` result produced by the operation.
    """
    return NoneBotEventProxy(binding, backend, context, reason=reason)


def bot_proxy_factory(
    *,
    binding: RuntimeBinding,
    backend: RuntimeApiBackend | None,
    context: RuntimeCallContext | None,
    reason: str = "unavailable",
) -> NoneBotBotProxy:
    """Implement the bot proxy factory operation for the component.

    Args:
        binding: The binding value used by the operation.
        backend: The backend value used by the operation.
        context: Runtime or authorization context for the operation.
        reason: The reason value used by the operation.

    Returns:
        The `NoneBotBotProxy` result produced by the operation.
    """
    return NoneBotBotProxy(binding, backend, context, reason=reason)


def _send_result(proxy: RuntimeNamespaceProxy, operation: str, value: JsonValue) -> SendResult:
    """Send result.

    Args:
        proxy: The proxy value used by the operation.
        operation: The operation value used by the operation.
        value: Value to validate, transform, or store.

    Returns:
        The `SendResult` result produced by the operation.

    Notes:
        Internal implementation detail for `_send_result`. It delegates to `model_validate` while
        keeping intermediate state local to the owning operation.
    """
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
