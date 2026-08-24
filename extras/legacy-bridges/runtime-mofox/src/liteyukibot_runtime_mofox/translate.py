"""Translation between Liteyuki envelopes and Neo-MoFox messages."""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any

from liteyukibot.events import EventEnvelope, Message, Segment


@dataclass(frozen=True, slots=True)
class MoFoxEventInput:
    """Represent the mo fox event input contract."""
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
        """Return the mo fox event input's text.

        Returns:
            The `str` result produced by the operation.
        """
        return self.message.plain_text


def to_mofox_event_input(event: EventEnvelope) -> MoFoxEventInput:
    """Convert the value to mofox event input.

    Args:
        event: Event associated with the operation.

    Returns:
        The `MoFoxEventInput` result produced by the operation.
    """
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
    """Build the documented ``mofox-wire`` envelope consumed by MessageReceiver.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `dict[str, Any]` result produced by the operation.
    """
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
    """Preserve portable segments while matching MoFox's scalar text wire shape.

    Args:
        segment: The segment value used by the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_to_mofox_segment`. It delegates to `model_dump` while
        keeping intermediate state local to the owning operation.
    """

    data = segment.model_dump(mode="json")["data"]
    assert isinstance(data, dict)
    if segment.type == "text":
        return {"type": "text", "data": data["text"]}
    return {"type": segment.type, "data": data}
