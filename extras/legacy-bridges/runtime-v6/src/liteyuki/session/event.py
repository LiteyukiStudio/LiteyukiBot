"""LiteyukiBot v6-compatible message event model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from liteyukibot.exceptions import LegacyUnsupportedError

type ReplyPayload = str | dict[str, Any]


class MessageEvent:
    """Represent the validated message event contract."""
    def __init__(
        self,
        bot_id: str,
        message: list[dict[str, Any]] | str,
        message_type: str,
        raw_message: str,
        session_id: str,
        user_id: str,
        session_type: str,
        receive_channel: object | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize the message event.

        Args:
            bot_id: Stable identifier for the bot.
            message: Message content associated with the operation.
            message_type: The message type value used by the operation.
            raw_message: The raw message value used by the operation.
            session_id: Stable identifier for the session.
            user_id: Stable identifier for the user.
            session_type: The session type value used by the operation.
            receive_channel: The receive channel value used by the operation.
            data: The data value used by the operation.

        Returns:
            None.
        """
        if receive_channel is not None:
            raise LegacyUnsupportedError(
                "MessageEvent.receive_channel relies on unsupported v6 Channel semantics; "
                "hosted v6 plugins must use event.reply()"
            )
        self.message_type = message_type
        self.data = dict(data or {})
        self.bot_id = bot_id
        self.message = message
        self.raw_message = raw_message
        self.session_id = session_id
        self.session_type = session_type
        self.user_id = user_id
        self.receive_channel = None
        self._replies: list[ReplyPayload] = []

    def __str__(self) -> str:
        """Implement the str operation for the message event.

        Returns:
            The `str` result produced by the operation.
        """
        return (
            f"Event(message_type={self.message_type}, data={self.data}, bot_id={self.bot_id}, "
            f"session_id={self.session_id}, session_type={self.session_type})"
        )

    @property
    def replies(self) -> tuple[ReplyPayload, ...]:
        """Return the message event's replies.

        Returns:
            The `tuple[ReplyPayload, ...]` result produced by the operation.
        """
        return tuple(self._replies)

    def reply(self, message: str | Mapping[str, Any]) -> None:
        """Implement the reply operation for the message event.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """
        if isinstance(message, str):
            payload: ReplyPayload = message
        elif isinstance(message, Mapping):
            payload = dict(message)
        else:
            raise TypeError("v6 replies must be a string or mapping")
        self._replies.append(payload)

    def _drain_replies(self) -> tuple[ReplyPayload, ...]:
        """Implement the drain replies operation for the message event.

        Returns:
            The `tuple[ReplyPayload, ...]` result produced by the operation.

        Notes:
            Internal implementation detail for `MessageEvent._drain_replies`. It delegates to `clear` while
            keeping intermediate state local to the owning operation.
        """
        replies = tuple(self._replies)
        self._replies.clear()
        return replies


__all__ = ["MessageEvent", "ReplyPayload"]
