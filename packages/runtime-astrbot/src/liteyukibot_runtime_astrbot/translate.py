"""Portable broker translation for native AstrBot platform messages."""

from __future__ import annotations

from typing import Any, Literal

from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope, Message, Segment, canonical_source_event_id


def to_event_envelope(event: Any, *, reply_token: str, runtime_id: str = "astrbot") -> EventEnvelope:
    """Project the stable public AstrBot event properties into a portable message."""

    message = getattr(event, "message_obj", None)
    platform_id = _identifier(event.get_platform_id(), "platform ID")
    bot_id = _identifier(event.get_self_id(), "bot ID")
    source_event_id = _identifier(getattr(message, "message_id", None), "message ID")
    group_id = str(event.get_group_id() or "").strip()
    conversation_id = group_id or _identifier(event.get_session_id(), "session ID")
    conversation_type: Literal["group", "private"] = "group" if group_id else "private"
    sender_id = str(event.get_sender_id() or "").strip()
    sender_name = str(event.get_sender_name() or "").strip() or None
    text = str(event.get_message_str() or "")
    segments = _segments(event.get_messages(), text)
    return EventEnvelope(
        id=canonical_source_event_id(runtime_id, f"{platform_id}:{bot_id}", source_event_id),
        runtime_id=runtime_id,
        adapter=_identifier(event.get_platform_name(), "platform name"),
        bot_id=bot_id,
        type="message.created",
        conversation=ConversationRef(id=conversation_id, type=conversation_type),
        actor=ActorRef(id=sender_id, display_name=sender_name) if sender_id else None,
        message=Message(segments=segments),
        reply_token=reply_token,
        raw={
            "astrbot": {
                "platform_id": platform_id,
                "source_event_id": source_event_id,
                "message_type": str(event.get_message_type()),
            }
        },
    )


def _segments(items: Any, text: str) -> tuple[Segment, ...]:
    rendered: list[Segment] = []
    for item in items:
        kind = type(item).__name__
        if kind == "Plain" and isinstance(getattr(item, "text", None), str):
            rendered.append(Segment(type="text", data={"text": item.text}))
        elif kind == "AtAll":
            rendered.append(Segment(type="mention", data={"scope": "all"}))
        elif kind == "At" and getattr(item, "qq", None) is not None:
            rendered.append(Segment(type="mention", data={"user_id": str(item.qq)}))
        elif kind == "Reply" and getattr(item, "id", None) is not None:
            rendered.append(Segment(type="reply", data={"message_id": str(item.id)}))
        elif kind in {"Image", "Record", "Video", "File"}:
            source = getattr(item, "url", None) or getattr(item, "file", None)
            if isinstance(source, str) and source:
                media_type = {"Image": "image", "Record": "voice", "Video": "video", "File": "file"}[kind]
                rendered.append(Segment(type="media", data={"media_type": media_type, "url": source}))
    if rendered:
        return tuple(rendered)
    if text:
        return (Segment(type="text", data={"text": text}),)
    raise ValueError("AstrBot message has no portable content")


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"AstrBot {name} must be a non-empty string")
    return value.strip()
