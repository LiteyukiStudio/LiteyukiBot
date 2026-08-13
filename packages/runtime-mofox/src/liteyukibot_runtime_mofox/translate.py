"""Translation between Liteyuki envelopes and Neo-MoFox messages."""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any

from liteyukibot.events import ActionEnvelope, EventEnvelope, Message, Segment, SendMessage


@dataclass(frozen=True, slots=True)
class MoFoxEventInput:
    runtime_id: str
    adapter: str
    bot_id: str
    event_id: str
    conversation_id: str
    conversation_type: str
    actor_id: str
    actor_name: str | None
    message: Message
    raw: dict[str, object]

    @property
    def text(self) -> str:
        return self.message.plain_text


def to_mofox_event_input(event: EventEnvelope) -> MoFoxEventInput:
    if event.message is None:
        raise ValueError("MoFox agent runtime only accepts message events")
    actor = event.actor
    return MoFoxEventInput(
        runtime_id=event.runtime_id,
        adapter=event.adapter,
        bot_id=event.bot_id,
        event_id=event.id,
        conversation_id=event.conversation.id,
        conversation_type=event.conversation.type,
        actor_id="" if actor is None else actor.id,
        actor_name=None if actor is None else actor.display_name,
        message=event.message,
        raw=event.model_dump(mode="json")["raw"],
    )


def to_mofox_envelope(value: MoFoxEventInput) -> dict[str, Any]:
    """Build the documented ``mofox-wire`` envelope consumed by MessageReceiver."""
    user_info: dict[str, str] = {
        "platform": f"liteyuki:{value.adapter}",
        "user_id": value.actor_id or "unknown",
        "user_nickname": value.actor_name or value.actor_id or "Unknown",
    }
    message_info: dict[str, Any] = {
        "platform": f"liteyuki:{value.adapter}",
        "message_id": value.event_id,
        "message_type": "message",
        "time": time(),
        "user_info": user_info,
        "extra": {
            "liteyuki_runtime_id": value.runtime_id,
            "liteyuki_bot_id": value.bot_id,
            "liteyuki_conversation_id": value.conversation_id,
        },
    }
    if value.conversation_type == "group":
        message_info["group_info"] = {
            "platform": f"liteyuki:{value.adapter}",
            "group_id": value.conversation_id,
            "group_name": value.conversation_id,
        }
    return {
        "direction": "incoming",
        "message_info": message_info,
        "message_segment": [_to_mofox_segment(segment) for segment in value.message.segments],
        "raw_message": {
            "liteyuki_runtime": value.runtime_id,
            "adapter": value.adapter,
            "source": value.raw,
        },
    }


def _to_mofox_segment(segment: Segment) -> dict[str, Any]:
    """Preserve portable segments while matching MoFox's scalar text wire shape."""

    data = segment.model_dump(mode="json")["data"]
    assert isinstance(data, dict)
    if segment.type == "text":
        return {"type": "text", "data": data["text"]}
    return {"type": segment.type, "data": data}


def to_send_action(event: EventEnvelope, message: Message | str) -> ActionEnvelope:
    if isinstance(message, str):
        if not message:
            raise ValueError("MoFox output text must not be empty")
        message = Message(segments=(Segment(type="text", data={"text": message}),))
    if not message.segments:
        raise ValueError("MoFox output message must not be empty")
    return ActionEnvelope(
        event_id=event.id,
        runtime_id=event.runtime_id,
        bot_id=event.bot_id,
        action=SendMessage(
            message=message,
            conversation=event.conversation,
            reply_token=event.reply_token,
        ),
    )
