from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from liteyukibot_runtime_astrbot.host import AstrBotRuntimeHost
from liteyukibot_runtime_astrbot.translate import to_astr_event_input, to_send_action

from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope, Message, Segment, SendMessage
from liteyukibot.runtime.protocol import ActionResponse, EventAccepted, EventMessage


def _event() -> EventEnvelope:
    return EventEnvelope(
        id="event-1",
        runtime_id="nonebot",
        adapter="onebot",
        bot_id="bot-1",
        type="message",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=ActorRef(id="user-1", display_name="User"),
        message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
        reply_token="reply-1",
    )


def test_astrbot_translation_preserves_source_identity_and_message_route() -> None:
    event = _event()

    translated = to_astr_event_input(event)
    action = to_send_action(event, "response")

    assert translated.runtime_id == "nonebot"
    assert translated.conversation_type == "group"
    assert translated.actor_id == "user-1"
    assert translated.text == "hello"
    assert action.runtime_id == "nonebot"
    assert action.event_id == "event-1"
    assert isinstance(action.action, SendMessage)
    assert action.action.reply_token == "reply-1"


def test_astrbot_translation_rejects_non_message_events() -> None:
    event = _event().model_copy(update={"message": None})

    with pytest.raises(ValueError, match="message events"):
        to_astr_event_input(event)


class FakeClient:
    def __init__(self) -> None:
        self.sent: list[object] = []
        self.actions: list[dict[str, object]] = []

    async def send(self, message: object) -> None:
        self.sent.append(message)

    async def execute_action(self, _correlation_id: str, payload: dict[str, object]) -> ActionResponse:
        self.actions.append(payload)
        return ActionResponse(correlation_id="action", ok=True)


class FakeEngine:
    async def process(self, event: EventEnvelope, sink: Callable[[str], Awaitable[None]]) -> None:
        assert event.id == "event-1"
        await sink("AstrBot response")

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_astrbot_host_returns_pipeline_output_to_the_source_runtime() -> None:
    client = FakeClient()
    host = AstrBotRuntimeHost(client, FakeEngine(), max_concurrent_events=1)  # type: ignore[arg-type]
    event = _event()

    await host._accept_event(EventMessage(correlation_id="delivery-1", payload=event.model_dump(mode="json")))
    await asyncio.gather(*host._tasks)
    await host.close()

    assert client.sent == [EventAccepted(correlation_id="delivery-1", status="accepted")]
    assert client.actions[0]["runtime_id"] == "nonebot"
    assert client.actions[0]["event_id"] == "event-1"
