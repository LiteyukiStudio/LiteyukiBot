"""Protocol-neutral OneBot v11 wire conversion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from liteyukibot_kernel import (
    ActorRef,
    ConversationRef,
    EventEnvelope,
    Message,
    Segment,
    canonical_source_event_id,
    json_value,
)

ONEBOT_V11_ADAPTER = "onebot.v11"


class OneBotV11Error(ValueError):
    """The OneBot v11 value or operation is not supported."""


def normalize_event(
    payload: Mapping[str, Any],
    *,
    self_id: str,
    runtime_id: str = "onebot",
    adapter: str = ONEBOT_V11_ADAPTER,
) -> EventEnvelope | None:
    """Convert one inbound OneBot v11 message event to a kernel envelope.

    Events outside ``post_type=message`` or outside private/group conversations
    are deliberately ignored. Invalid fields on an otherwise supported event
    raise :class:`OneBotV11Error` so the owning transport can discard only that
    frame.
    """

    if payload.get("post_type") != "message":
        return None
    message_type = _required_string(payload, "message_type")
    if message_type not in {"private", "group"}:
        return None

    event_self_id = payload.get("self_id")
    if event_self_id is not None and _identifier(event_self_id, "self_id") != self_id:
        raise OneBotV11Error("OneBot event self_id does not match the configured account")

    message_id = _identifier(payload.get("message_id"), "message_id")
    user_id = _identifier(payload.get("user_id"), "user_id")
    conversation_id = _identifier(
        payload.get("group_id") if message_type == "group" else payload.get("user_id"),
        "group_id" if message_type == "group" else "user_id",
    )
    subtype = payload.get("sub_type", "normal")
    if not isinstance(subtype, str) or not subtype:
        subtype = "normal"

    sender = payload.get("sender")
    display_name = None
    if isinstance(sender, Mapping):
        display_name = _optional_string(sender.get("card")) or _optional_string(sender.get("nickname"))

    conversation_type: Literal["private", "group"] = "group" if message_type == "group" else "private"
    source_scope = f"{ONEBOT_V11_ADAPTER}:{self_id}"
    values: dict[str, Any] = {
        "id": canonical_source_event_id(runtime_id, source_scope, message_id),
        "runtime_id": runtime_id,
        "adapter": adapter,
        "bot_id": self_id,
        "type": f"message.{conversation_type}.{subtype}",
        "conversation": ConversationRef(id=conversation_id, type=conversation_type),
        "actor": ActorRef(id=user_id, display_name=display_name, is_bot=user_id == self_id),
        "message": to_portable_message(payload.get("message")),
        "reply_token": str(uuid4()),
        "raw": json_value(payload),
    }
    timestamp = payload.get("time")
    if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
        try:
            values["timestamp"] = datetime.fromtimestamp(timestamp, UTC)
        except (OverflowError, OSError, ValueError) as error:
            raise OneBotV11Error("OneBot event time is outside the supported range") from error
    return EventEnvelope.model_validate(values)


def to_portable_message(value: Any) -> Message:
    """Convert a OneBot v11 string or segment array to a kernel message."""

    if isinstance(value, str):
        return Message(segments=(Segment(type="text", data={"text": value}),))
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise OneBotV11Error("OneBot v11 message must be a string or segment array")

    segments: list[Segment] = []
    for raw_segment in value:
        if not isinstance(raw_segment, Mapping):
            raise OneBotV11Error("OneBot v11 message segments must be objects")
        native_type = _required_string(raw_segment, "type")
        raw_data = raw_segment.get("data", {})
        if not isinstance(raw_data, Mapping):
            raise OneBotV11Error("OneBot v11 segment data must be an object")
        data = json_value(raw_data)
        if not isinstance(data, Mapping):
            raise OneBotV11Error("OneBot v11 segment data must serialize to an object")
        segments.append(_to_portable_segment(native_type, dict(data)))
    return Message(segments=tuple(segments))


def _to_portable_segment(native_type: str, data: dict[str, Any]) -> Segment:
    if native_type == "text":
        text = data.get("text")
        if not isinstance(text, str):
            raise OneBotV11Error("OneBot v11 text segments require data.text")
        return Segment(type="text", data={"text": text})
    if native_type in {"at", "mention"}:
        target = data.get("qq", data.get("user_id"))
        if target == "all":
            return Segment(type="mention", data={"scope": "all"})
        return Segment(type="mention", data={"user_id": _identifier(target, "mention user_id")})
    if native_type == "reply":
        return Segment(type="reply", data={"message_id": _identifier(data.get("id"), "reply id")})
    if native_type == "image":
        source = data.get("url") or data.get("file")
        if not isinstance(source, str) or not source:
            raise OneBotV11Error("OneBot v11 image segments require data.file or data.url")
        return Segment(type="image", data={"url": source})
    raise OneBotV11Error(f"unsupported OneBot v11 segment type {native_type!r}")


def to_onebot_message(message: Message) -> list[dict[str, Any]]:
    """Convert a kernel message to OneBot v11 array form."""

    return [_to_onebot_segment(segment) for segment in message.segments]


def _to_onebot_segment(segment: Segment) -> dict[str, Any]:
    data = dict(segment.model_dump(mode="json")["data"])
    if segment.type == "text":
        text = data.get("text")
        if not isinstance(text, str):
            raise OneBotV11Error("text segments require data.text")
        return {"type": "text", "data": {"text": text}}
    if segment.type == "mention":
        scope = data.get("scope")
        if scope == "all":
            return {"type": "at", "data": {"qq": "all"}}
        user_id = data.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise OneBotV11Error("OneBot v11 mentions require user_id or scope=all")
        return {"type": "at", "data": {"qq": user_id}}
    if segment.type == "reply":
        message_id = data.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            raise OneBotV11Error("reply segments require a non-empty message_id")
        return {"type": "reply", "data": {"id": message_id}}
    if segment.type == "image":
        source = data.get("file") or data.get("url")
        if not isinstance(source, str) or not source:
            raise OneBotV11Error("OneBot v11 images require data.file or data.url")
        return {"type": "image", "data": {"file": source}}
    raise OneBotV11Error(f"unsupported portable segment type {segment.type!r}")


def _required_string(value: Mapping[str, Any], key: str) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) or not candidate:
        raise OneBotV11Error(f"OneBot event requires string {key}")
    return candidate


def _identifier(value: Any, name: str) -> str:
    if value is None or isinstance(value, bool):
        raise OneBotV11Error(f"OneBot event requires {name}")
    if isinstance(value, (str, int)):
        identifier = str(value)
    else:
        raise OneBotV11Error(f"OneBot event requires {name}")
    if not identifier or identifier != identifier.strip():
        raise OneBotV11Error(f"OneBot event requires a non-empty {name}")
    return identifier


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


__all__ = [
    "ONEBOT_V11_ADAPTER",
    "OneBotV11Error",
    "normalize_event",
    "to_onebot_message",
    "to_portable_message",
]
