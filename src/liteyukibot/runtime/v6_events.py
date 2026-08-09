"""Pure event and reply translation for the v6 compatibility runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from liteyuki.session import MessageEvent, ReplyPayload

from ..events import ActionEnvelope, EventEnvelope, Message, Segment, SendMessage

_PORTABLE_SEGMENT_TYPES = frozenset({"text", "media", "mention", "reply", "adapter"})


def to_legacy_message_event(envelope: EventEnvelope) -> MessageEvent | None:
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


def reply_to_action(reply: ReplyPayload, envelope: EventEnvelope) -> ActionEnvelope:
    message = _reply_message(reply)
    return ActionEnvelope(
        event_id=envelope.id,
        runtime_id=envelope.runtime_id,
        bot_id=envelope.bot_id,
        action=SendMessage(
            message=message,
            conversation=envelope.conversation,
            reply_token=envelope.reply_token,
        ),
    )


def _reply_message(reply: ReplyPayload) -> Message:
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
    return {str(key): _json_value(item) for key, item in value.items()}


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _json_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


__all__ = ["reply_to_action", "to_legacy_message_event"]
