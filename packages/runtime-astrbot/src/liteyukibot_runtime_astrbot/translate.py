"""Framework-independent translation between Liteyuki envelopes and AstrBot input."""

from __future__ import annotations

from dataclasses import dataclass

from liteyukibot.events import ActionEnvelope, EventEnvelope, Message, Segment, SendMessage


@dataclass(frozen=True, slots=True)
class AstrEventInput:
    runtime_id: str
    adapter: str
    bot_id: str
    event_id: str
    conversation_id: str
    conversation_type: str
    actor_id: str
    actor_name: str | None
    text: str


def to_astr_event_input(event: EventEnvelope) -> AstrEventInput:
    if event.message is None:
        raise ValueError("AstrBot agent runtime only accepts message events")
    actor = event.actor
    return AstrEventInput(
        runtime_id=event.runtime_id,
        adapter=event.adapter,
        bot_id=event.bot_id,
        event_id=event.id,
        conversation_id=event.conversation.id,
        conversation_type=event.conversation.type,
        actor_id="" if actor is None else actor.id,
        actor_name=None if actor is None else actor.display_name,
        text=event.message.plain_text,
    )


def to_send_action(event: EventEnvelope, text: str) -> ActionEnvelope:
    if not text:
        raise ValueError("AstrBot output text must not be empty")
    return ActionEnvelope(
        event_id=event.id,
        runtime_id=event.runtime_id,
        bot_id=event.bot_id,
        action=SendMessage(
            message=Message(segments=(Segment(type="text", data={"text": text}),)),
            conversation=event.conversation,
            reply_token=event.reply_token,
        ),
    )
