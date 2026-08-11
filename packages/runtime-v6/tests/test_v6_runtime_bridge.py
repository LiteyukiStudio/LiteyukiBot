from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any, cast

import pytest
from _support import FakeLogger
from liteyuki.session import MessageEvent, on_message
from liteyuki.session.on import _reset_matchers
from liteyukibot_runtime_v6.events import reply_to_action, to_legacy_message_event
from liteyukibot_runtime_v6.host import _V6RuntimeHost

from liteyukibot.events import (
    ActorRef,
    ConversationRef,
    EventEnvelope,
    Message,
    Segment,
    SendMessage,
)
from liteyukibot.runtime import RuntimeClient
from liteyukibot.runtime.protocol import ActionResponse, EventAccepted, EventCompleted, EventMessage


@pytest.fixture(autouse=True)
def reset_matchers() -> Iterator[None]:
    _reset_matchers()
    yield
    _reset_matchers()


def _envelope(*, message: Message | None = None, actor: ActorRef | None = None) -> EventEnvelope:
    return EventEnvelope(
        id="event-1",
        runtime_id="adapter",
        adapter="onebot-v11",
        bot_id="bot-1",
        type="message.group.normal",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=actor if actor is not None else ActorRef(id="user-1"),
        message=message
        if message is not None
        else Message(
            segments=(
                Segment(type="text", data={"text": "hello"}),
                Segment(type="mention", data={"user_id": "bot-1"}),
            )
        ),
        reply_token="reply-token",
        raw={"nested": {"value": 1}},
    )


def test_event_envelope_maps_to_legacy_message_event_with_deep_json_copy() -> None:
    envelope = _envelope()

    event = to_legacy_message_event(envelope)

    assert event is not None
    assert event.bot_id == "bot-1"
    assert event.message_type == "message.group.normal"
    assert event.message == [
        {"type": "text", "data": {"text": "hello"}},
        {"type": "mention", "data": {"user_id": "bot-1"}},
    ]
    assert event.raw_message == "hello"
    assert event.session_id == "group-1"
    assert event.session_type == "group"
    assert event.user_id == "user-1"
    assert event.data == {"nested": {"value": 1}}

    nested = cast(dict[str, Any], event.data["nested"])
    nested["value"] = 2
    assert envelope.model_dump(mode="json")["raw"] == {"nested": {"value": 1}}


def test_event_mapping_handles_missing_actor_and_message() -> None:
    without_actor = _envelope(actor=ActorRef(id="temporary"))
    payload = without_actor.model_dump(mode="json")
    payload["actor"] = None
    event = to_legacy_message_event(EventEnvelope.model_validate(payload))
    no_message_payload = without_actor.model_dump(mode="json")
    no_message_payload["message"] = None

    assert event is not None
    assert event.user_id == ""
    assert to_legacy_message_event(EventEnvelope.model_validate(no_message_payload)) is None


def test_reply_intents_translate_to_ordered_protocol_neutral_actions() -> None:
    envelope = _envelope()

    text = reply_to_action("hello", envelope)
    mention = reply_to_action(
        {"type": "mention", "data": {"user_id": "user-2"}},
        envelope,
    )
    image = reply_to_action(
        {"type": "image", "data": {"url": "https://example.invalid/image.png"}},
        envelope,
    )

    assert len({text.action_id, mention.action_id, image.action_id}) == 3
    for action in (text, mention, image):
        assert action.event_id == "event-1"
        assert action.runtime_id == "adapter"
        assert action.bot_id == "bot-1"
        assert isinstance(action.action, SendMessage)
        assert action.action.conversation == envelope.conversation
        assert action.action.reply_token == "reply-token"
    assert isinstance(text.action, SendMessage)
    assert isinstance(mention.action, SendMessage)
    assert isinstance(image.action, SendMessage)
    assert text.action.message.plain_text == "hello"
    assert mention.action.message.segments[0] == Segment(
        type="mention",
        data={"user_id": "user-2"},
    )
    assert image.action.message.segments[0] == Segment(
        type="adapter",
        data={
            "type": "image",
            "data": {"url": "https://example.invalid/image.png"},
        },
    )

    with pytest.raises(ValueError, match="non-empty string type"):
        reply_to_action({"data": {}}, envelope)
    with pytest.raises(ValueError, match="object data field"):
        reply_to_action({"type": "text", "data": "invalid"}, envelope)


class _FakeClient:
    def __init__(self, responses: list[ActionResponse] | None = None) -> None:
        self.sent: list[object] = []
        self.actions: list[tuple[str, dict[str, Any]]] = []
        self.responses = list(responses or [])

    async def send(self, message: object) -> None:
        self.sent.append(message)

    async def execute_action(
        self,
        correlation_id: str,
        payload: dict[str, Any],
        timeout_seconds: float = 30.0,
    ) -> ActionResponse:
        self.actions.append((correlation_id, payload))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_v6_host_preserves_reply_order_and_isolates_action_failure() -> None:
    matcher = on_message()

    @matcher.handle()
    async def reply(event: MessageEvent) -> None:
        event.reply("first")
        event.reply({"type": "text", "data": {"text": "second"}})

    client = _FakeClient(
        [
            ActionResponse(correlation_id="ignored", ok=False, error="failed"),
            ActionResponse(correlation_id="ignored", ok=True),
        ]
    )
    host = _V6RuntimeHost(
        cast(RuntimeClient, client),
        FakeLogger(),
        max_concurrent_events=2,
        action_timeout_seconds=1,
    )

    await host._process_event(
        EventMessage(
            correlation_id="delivery-1",
            payload=_envelope().model_dump(mode="json"),
        )
    )

    assert len(client.actions) == 2
    actions = [payload for _correlation_id, payload in client.actions]
    assert actions[0]["action"]["message"]["segments"][0]["data"]["text"] == "first"
    assert actions[1]["action"]["message"]["segments"][0]["data"]["text"] == "second"
    assert client.sent == [
        EventAccepted(correlation_id="delivery-1", status="accepted"),
        EventCompleted(correlation_id="delivery-1", status="completed"),
    ]


@pytest.mark.asyncio
async def test_v6_host_accepts_non_message_and_rejects_malformed_event() -> None:
    calls = 0

    @on_message().handle()
    async def observe(_event: MessageEvent) -> None:
        nonlocal calls
        calls += 1

    client = _FakeClient()
    host = _V6RuntimeHost(
        cast(RuntimeClient, client),
        FakeLogger(),
        max_concurrent_events=1,
        action_timeout_seconds=1,
    )
    payload = _envelope().model_dump(mode="json")
    payload["message"] = None

    await host._process_event(EventMessage(correlation_id="notice", payload=payload))
    await host._process_event(EventMessage(correlation_id="invalid", payload={"invalid": True}))

    assert calls == 0
    assert client.sent == [
        EventAccepted(correlation_id="notice", status="accepted"),
        EventCompleted(correlation_id="notice", status="completed"),
        EventAccepted(
            correlation_id="invalid",
            status="invalid",
            detail="invalid EventEnvelope",
        ),
    ]


@pytest.mark.asyncio
async def test_v6_host_rejects_event_when_capacity_is_exhausted() -> None:
    client = _FakeClient()
    host = _V6RuntimeHost(
        cast(RuntimeClient, client),
        FakeLogger(),
        max_concurrent_events=1,
        action_timeout_seconds=1,
    )
    release = asyncio.Event()
    pending = asyncio.create_task(release.wait())
    host._event_tasks.add(cast(asyncio.Task[None], pending))

    await host._accept_event(
        EventMessage(
            correlation_id="overloaded",
            payload=_envelope().model_dump(mode="json"),
        )
    )
    await host.close()

    assert client.sent == [
        EventAccepted(
            correlation_id="overloaded",
            status="overloaded",
            detail="v6 runtime event capacity is exhausted",
        )
    ]
