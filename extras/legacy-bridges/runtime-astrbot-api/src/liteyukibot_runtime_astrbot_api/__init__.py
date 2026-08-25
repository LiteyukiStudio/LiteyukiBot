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
        """Return the astr bot event snapshot's platform id.

        Returns:
            The `str` result produced by the operation.
        """
        return _extension_text(self, "platform_id")

    @property
    def platform_name(self) -> str:
        """Return the astr bot event snapshot's platform name.

        Returns:
            The `str` result produced by the operation.
        """
        return _extension_text(self, "platform_name")

    @property
    def session_id(self) -> str:
        """Return the astr bot event snapshot's session id.

        Returns:
            The `str` result produced by the operation.
        """
        return _extension_text(self, "session_id")

    @property
    def group_id(self) -> str | None:
        """Return the astr bot event snapshot's group id.

        Returns:
            The `str | None` result produced by the operation.
        """
        return self.conversation.id if self.conversation.type == "group" else None

    @property
    def sender_id(self) -> str | None:
        """Return the astr bot event snapshot's sender id.

        Returns:
            The `str | None` result produced by the operation.
        """
        return None if self.actor is None else self.actor.id

    @property
    def message_text(self) -> str:
        """Return the astr bot event snapshot's message text.

        Returns:
            The `str` result produced by the operation.
        """
        return "" if self.message is None else self.message.plain_text

    @property
    def message_type(self) -> str:
        """Return the astr bot event snapshot's message type.

        Returns:
            The `str` result produced by the operation.
        """
        return _extension_text(self, "message_type")

    @property
    def conversation_id(self) -> str:
        """Return the astr bot event snapshot's conversation id.

        Returns:
            The `str` result produced by the operation.
        """
        return self.conversation.id

    @property
    def conversation_type(self) -> str:
        """Return the astr bot event snapshot's conversation type.

        Returns:
            The `str` result produced by the operation.
        """
        return self.conversation.type

    @property
    def actor_name(self) -> str | None:
        """Return the astr bot event snapshot's actor name.

        Returns:
            The `str | None` result produced by the operation.
        """
        return None if self.actor is None else self.actor.display_name

    @property
    def actor_is_bot(self) -> bool:
        """Return the astr bot event snapshot's actor is bot.

        Returns:
            Whether the requested condition is satisfied.
        """
        return False if self.actor is None else self.actor.is_bot

    @property
    def message_segments(self) -> tuple[Segment, ...]:
        """Return the astr bot event snapshot's message segments.

        Returns:
            The `tuple[Segment, ...]` result produced by the operation.
        """
        return () if self.message is None else self.message.segments


class AstrBotBotSnapshot(BotSnapshot):
    """Canonical bot snapshot with Alpha9 AstrBot field compatibility properties."""

    @property
    def platform_id(self) -> str:
        """Return the astr bot bot snapshot's platform id.

        Returns:
            The `str` result produced by the operation.
        """
        return _extension_text(self, "platform_id")

    @property
    def platform_name(self) -> str:
        """Return the astr bot bot snapshot's platform name.

        Returns:
            The `str` result produced by the operation.
        """
        return _extension_text(self, "platform_name")


class AstrBotEventProxy(RuntimeNamespaceProxy):
    """Typed facade for the portable AstrBot event contract."""

    async def snapshot(self) -> AstrBotEventSnapshot:
        """Return an immutable snapshot of the astr bot event proxy state.

        Returns:
            The requested `AstrBotEventSnapshot` value.
        """
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
        """Send the astr bot event proxy operation.

        Args:
            message: Message content associated with the operation.

        Returns:
            The `SendResult` result produced by the operation.
        """
        return await self._send(message)

    async def send_message(self, message: Message) -> SendResult:
        """Send message.

        Args:
            message: Message content associated with the operation.

        Returns:
            The `SendResult` result produced by the operation.
        """
        return await self._send(message)

    async def _send(self, message: str | Message) -> SendResult:
        """Send the astr bot event proxy operation.

        Args:
            message: Message content associated with the operation.

        Returns:
            The `SendResult` result produced by the operation.

        Notes:
            Internal implementation detail for `AstrBotEventProxy._send`. It delegates to `cast`,
            `model_dump`, `call`, `_send_result` while keeping intermediate state local to the owning
            operation.
        """
        argument: JsonValue = message if isinstance(message, str) else cast(
            dict[str, JsonValue], message.model_dump(mode="json")
        )
        value = await self.call("send", {"message": argument})
        return _send_result(self, "send", value)


class AstrBotBotProxy(RuntimeNamespaceProxy):
    """Typed facade for exact-bot identity and portable proactive sending."""

    async def snapshot(self) -> AstrBotBotSnapshot:
        """Return an immutable snapshot of the astr bot bot proxy state.

        Returns:
            The requested `AstrBotBotSnapshot` value.
        """
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
        """Send the astr bot bot proxy operation.

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


def proxy_factory(
    *,
    binding: RuntimeBinding,
    backend: RuntimeApiBackend | None,
    context: RuntimeCallContext | None,
    reason: str = "unavailable",
) -> AstrBotEventProxy:
    """Implement the proxy factory operation for the component.

    Args:
        binding: The binding value used by the operation.
        backend: The backend value used by the operation.
        context: Runtime or authorization context for the operation.
        reason: The reason value used by the operation.

    Returns:
        The `AstrBotEventProxy` result produced by the operation.
    """
    return AstrBotEventProxy(binding, backend, context, reason=reason)


def bot_proxy_factory(
    *,
    binding: RuntimeBinding,
    backend: RuntimeApiBackend | None,
    context: RuntimeCallContext | None,
    reason: str = "unavailable",
) -> AstrBotBotProxy:
    """Implement the bot proxy factory operation for the component.

    Args:
        binding: The binding value used by the operation.
        backend: The backend value used by the operation.
        context: Runtime or authorization context for the operation.
        reason: The reason value used by the operation.

    Returns:
        The `AstrBotBotProxy` result produced by the operation.
    """
    return AstrBotBotProxy(binding, backend, context, reason=reason)


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


def _extension_text(snapshot: EventSnapshot | BotSnapshot, key: str) -> str:
    """Implement the extension text operation for the component.

    Args:
        snapshot: The snapshot value used by the operation.
        key: Stable FIFO ordering key for the queued work.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_extension_text`. It delegates to `get` while keeping
        intermediate state local to the owning operation.
    """
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
