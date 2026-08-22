"""Pure event and reply translation for the v6 compatibility runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from liteyuki.session import MessageEvent, ReplyPayload

from liteyukibot.events import EventEnvelope, Message, Segment

_PORTABLE_SEGMENT_TYPES = frozenset({"text", "media", "mention", "reply", "adapter"})


def to_legacy_message_event(envelope: EventEnvelope) -> MessageEvent | None:
    """Convert the value to legacy message event.

    Args:
        envelope: The envelope value used by the operation.

    Returns:
        The `MessageEvent | None` result produced by the operation.
    """
    if envelope.message is None:
        return None
    dumped = envelope.model_dump(mode="json")
    message = dumped["message"]
    assert isinstance(message, dict)
    segments = message["segments"]
    assert isinstance(segments, list)
    raw = dumped["raw"]
    assert isinstance(raw, dict)
    return MessageEvent(
        bot_id=envelope.bot_id,
        message=segments,
        message_type=envelope.type,
        raw_message=envelope.message.plain_text,
        session_id=envelope.conversation.id,
        user_id=envelope.actor.id if envelope.actor is not None else "",
        session_type=envelope.conversation.type,
        data=raw,
    )


def reply_to_message(reply: ReplyPayload) -> Message:
    """Convert one v6 reply intent into the portable broker message body.

    Args:
        reply: The reply value used by the operation.

    Returns:
        The `Message` result produced by the operation.
    """

    return _reply_message(reply)


def _reply_message(reply: ReplyPayload) -> Message:
    """Implement the reply message operation for the component.

    Args:
        reply: The reply value used by the operation.

    Returns:
        The `Message` result produced by the operation.

    Notes:
        Internal implementation detail for `_reply_message`. It delegates to `get`, `_json_mapping`,
        `model_validate` while keeping intermediate state local to the owning operation.
    """
    if isinstance(reply, str):
        return Message(segments=(Segment(type="text", data={"text": reply}),))

    segment_type = reply.get("type")
    data = reply.get("data")
    if not isinstance(segment_type, str) or not segment_type:
        raise ValueError("v6 mapping replies require a non-empty string type")
    if not isinstance(data, Mapping):
        raise ValueError("v6 mapping replies require an object data field")
    normalized_data = _json_mapping(data)
    if segment_type in _PORTABLE_SEGMENT_TYPES:
        segment = Segment.model_validate({"type": segment_type, "data": normalized_data})
    else:
        segment = Segment(
            type="adapter",
            data={"type": segment_type, "data": normalized_data},
        )
    return Message(segments=(segment,))


def _json_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Implement the json mapping operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_json_mapping`. It delegates to `_json_value`, `items` while
        keeping intermediate state local to the owning operation.
    """
    return {str(key): _json_value(item) for key, item in value.items()}


def _json_value(value: Any) -> Any:
    """Implement the json value operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_json_value`. It delegates to `_json_mapping`, `_json_value`
        while keeping intermediate state local to the owning operation.
    """
    if isinstance(value, Mapping):
        return _json_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


__all__ = ["reply_to_message", "to_legacy_message_event"]
