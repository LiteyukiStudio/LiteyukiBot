"""Protocol-neutral OneBot v11 wire conversion."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import uuid4

from liteyukibot_kernel import (
    ActorRef,
    ConversationRef,
    EventEnvelope,
    Message,
    Segment,
    canonical_source_event_id,
    json_mapping,
    json_value,
)

ONEBOT_V11_ADAPTER = "onebot.v11"
_CQ_CODE_PATTERN = re.compile(r"\[CQ:([A-Za-z][A-Za-z0-9_]*)(?:,([^\]]*))?\]")
_EVENT_ENVELOPE_FIELDS = frozenset({"time", "self_id", "post_type"})
_MEDIA_SOURCE_PREFIXES = ("http://", "https://", "file://", "base64://", "data:")


class OneBotV11Error(ValueError):
    """The OneBot v11 value or operation is not supported."""


def normalize_event(
    payload: Mapping[str, Any],
    *,
    self_id: str,
    runtime_id: str = "onebot",
    adapter: str = ONEBOT_V11_ADAPTER,
) -> EventEnvelope | None:
    """Convert one inbound OneBot v11 message, notice, or request event."""

    post_type = payload.get("post_type")
    if post_type not in {"message", "notice", "request"}:
        return None

    event_self_id = payload.get("self_id")
    if event_self_id is not None and _identifier(event_self_id, "self_id") != self_id:
        raise OneBotV11Error("OneBot event self_id does not match the configured account")

    try:
        event_timestamp = _event_timestamp(payload)
        if post_type == "message":
            return _normalize_message_event(
                payload,
                self_id=self_id,
                runtime_id=runtime_id,
                adapter=adapter,
                event_timestamp=event_timestamp,
            )
        return _normalize_signal_event(
            payload,
            self_id=self_id,
            runtime_id=runtime_id,
            adapter=adapter,
            post_type=post_type,
            event_timestamp=event_timestamp,
        )
    except OneBotV11Error:
        raise
    except (TypeError, ValueError) as error:
        raise OneBotV11Error("OneBot event contains invalid data") from error


def _normalize_message_event(
    payload: Mapping[str, Any],
    *,
    self_id: str,
    runtime_id: str,
    adapter: str,
    event_timestamp: datetime,
) -> EventEnvelope | None:
    message_type = _required_string(payload, "message_type")
    if message_type not in {"private", "group"}:
        return None

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
    parent_id = _temporary_session_parent_id(payload, sender, message_type=message_type, subtype=subtype)
    source_scope = f"{ONEBOT_V11_ADAPTER}:{self_id}"
    values: dict[str, Any] = {
        "id": canonical_source_event_id(runtime_id, source_scope, message_id),
        "runtime_id": runtime_id,
        "adapter": adapter,
        "bot_id": self_id,
        "type": f"message.{conversation_type}.{subtype}",
        "conversation": ConversationRef(id=conversation_id, type=conversation_type, parent_id=parent_id),
        "actor": ActorRef(id=user_id, display_name=display_name, is_bot=user_id == self_id),
        "message": to_portable_message(payload.get("message")),
        "reply_token": str(uuid4()),
        "details": _event_details(payload),
        "raw": json_value(payload),
        "timestamp": event_timestamp,
    }
    return EventEnvelope.model_validate(values)


def _normalize_signal_event(
    payload: Mapping[str, Any],
    *,
    self_id: str,
    runtime_id: str,
    adapter: str,
    post_type: str,
    event_timestamp: datetime,
) -> EventEnvelope:
    discriminator = "notice_type" if post_type == "notice" else "request_type"
    event_type = _required_string(payload, discriminator)
    subtype = _optional_string(payload.get("sub_type"))
    type_name = f"{post_type}.{event_type}" + (f".{subtype}" if subtype is not None else "")
    conversation = _signal_conversation(payload, post_type=post_type, event_type=event_type)
    actor_id = _signal_actor_id(payload, post_type=post_type)
    actor = None if actor_id is None else ActorRef(id=actor_id, is_bot=actor_id == self_id)
    return EventEnvelope.model_validate(
        {
            "runtime_id": runtime_id,
            "adapter": adapter,
            "bot_id": self_id,
            "type": type_name,
            "conversation": conversation,
            "actor": actor,
            "details": _event_details(payload),
            "raw": json_mapping(payload),
            "timestamp": event_timestamp,
        }
    )


def _event_timestamp(payload: Mapping[str, Any]) -> datetime:
    timestamp = payload.get("time")
    if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool):
        raise OneBotV11Error("OneBot event requires numeric time")
    if isinstance(timestamp, float) and not math.isfinite(timestamp):
        raise OneBotV11Error("OneBot event time must be finite")
    try:
        return datetime.fromtimestamp(timestamp, UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise OneBotV11Error("OneBot event time is outside the supported range") from error


def _event_details(payload: Mapping[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    excluded = _EVENT_ENVELOPE_FIELDS | ({"message", "sender"} if payload.get("post_type") == "message" else set())
    for key, value in payload.items():
        if key in excluded:
            continue
        if key.endswith("_id") and value is not None:
            details[key] = _identifier(value, key)
        else:
            details[key] = json_value(value)
    return details


def _signal_conversation(
    payload: Mapping[str, Any],
    *,
    post_type: str,
    event_type: str,
) -> ConversationRef | None:
    group_id = payload.get("group_id")
    if group_id is not None:
        return ConversationRef(id=_identifier(group_id, "group_id"), type="group")
    if post_type == "notice" and event_type in {"bot_offline", "profile_like"}:
        return None
    user_id = payload.get("user_id")
    if user_id is not None:
        return ConversationRef(id=_identifier(user_id, "user_id"), type="private")
    return None


def _signal_actor_id(payload: Mapping[str, Any], *, post_type: str) -> str | None:
    keys = ("user_id",) if post_type == "request" else ("sender_id", "operator_id", "user_id")
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return _identifier(value, key)
    return None


def to_portable_message(value: Any) -> Message:
    """Convert a OneBot v11 CQ string or segment array to a kernel message."""

    if isinstance(value, str):
        return _to_portable_cq_message(value)
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


def _to_portable_cq_message(value: str) -> Message:
    """Convert a legacy OneBot v11 CQ string."""

    segments: list[Segment] = []
    last_end = 0
    matched = False
    for match in _CQ_CODE_PATTERN.finditer(value):
        matched = True
        _append_cq_text(segments, value[last_end : match.start()])
        native_type = match.group(1).lower()
        data = _parse_cq_data(match.group(2) or "")
        segments.append(_to_portable_segment(native_type, data))
        last_end = match.end()
    _append_cq_text(segments, value[last_end:])
    if not matched:
        return Message(segments=(Segment(type="text", data={"text": _cq_unescape(value)}),))
    return Message(segments=tuple(segments))


def _append_cq_text(segments: list[Segment], value: str) -> None:
    text = _cq_unescape(value)
    if text:
        segments.append(Segment(type="text", data={"text": text}))


def _parse_cq_data(raw: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for pair in raw.split(","):
        key, separator, value = pair.partition("=")
        if separator and key:
            data[key] = _cq_unescape(value)
    return data


def _cq_unescape(value: str) -> str:
    return (
        value.replace("&#91;", "[")
        .replace("&#93;", "]")
        .replace("&#44;", ",")
        .replace("&amp;", "&")
    )


def _temporary_session_parent_id(
    payload: Mapping[str, Any],
    sender: Any,
    *,
    message_type: str,
    subtype: str,
) -> str | None:
    if message_type != "private" or subtype != "group":
        return None
    sender_group_id = sender.get("group_id") if isinstance(sender, Mapping) else None
    group_id = sender_group_id if sender_group_id is not None else payload.get("group_id")
    return None if group_id is None else _identifier(group_id, "group_id")


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
    if native_type in {"image", "record", "video", "file"}:
        portable_type = cast(
            Literal["image", "audio", "video", "file"],
            "audio" if native_type == "record" else native_type,
        )
        return Segment(type=portable_type, data=_portable_media_data(data, native_type=native_type))
    if native_type == "face":
        return Segment(type="emoji", data={"id": _identifier(data.get("id"), "face id")})
    return Segment(
        type="adapter",
        data={"adapter": ONEBOT_V11_ADAPTER, "type": native_type, "data": data},
    )


def _portable_media_data(data: dict[str, Any], *, native_type: str) -> dict[str, Any]:
    portable = dict(data)
    file_id = portable.pop("file_id", None)
    file_value = portable.pop("file", None)
    url = portable.get("url")
    if isinstance(url, str) and url:
        portable["url"] = url
        if file_id is not None:
            portable["file_id"] = _identifier(file_id, f"{native_type} file_id")
        elif isinstance(file_value, str) and file_value and not (
            file_value.startswith(_MEDIA_SOURCE_PREFIXES) or "/" in file_value or "\\" in file_value
        ):
            portable["file_id"] = file_value
    elif isinstance(file_value, str) and file_value:
        if file_value.startswith(_MEDIA_SOURCE_PREFIXES) or "/" in file_value or "\\" in file_value:
            portable["url"] = file_value
        else:
            portable["file_id"] = file_value
    elif file_id is not None:
        portable["file_id"] = _identifier(file_id, f"{native_type} file_id")
    else:
        raise OneBotV11Error(f"OneBot v11 {native_type} segments require data.file, data.file_id, or data.url")
    return portable


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
        return {"type": "image", "data": _onebot_media_data(data)}
    if segment.type == "audio":
        return {"type": "record", "data": _onebot_media_data(data)}
    if segment.type in {"video", "file"}:
        return {"type": segment.type, "data": _onebot_media_data(data)}
    if segment.type == "emoji":
        return {"type": "face", "data": {"id": data["id"]}}
    if segment.type == "adapter":
        target = data.get("adapter")
        native_type = data.get("type")
        native_data = data.get("data")
        if target != ONEBOT_V11_ADAPTER:
            raise OneBotV11Error("adapter segments must target onebot.v11")
        if not isinstance(native_type, str) or not native_type or not isinstance(native_data, Mapping):
            raise OneBotV11Error("adapter segments require a native type and object data")
        return {"type": native_type, "data": dict(native_data)}
    raise OneBotV11Error(f"unsupported portable segment type {segment.type!r}")


def _onebot_media_data(data: dict[str, Any]) -> dict[str, Any]:
    native = dict(data)
    file_id = native.pop("file_id", None)
    url = native.pop("url", None)
    source = file_id if isinstance(file_id, str) and file_id else url
    if not isinstance(source, str) or not source:
        raise OneBotV11Error("OneBot v11 media requires data.url or data.file_id")
    native["file"] = source
    return native


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
