from __future__ import annotations

import asyncio
import importlib.metadata
from collections.abc import Iterator
from typing import Any, cast

import pytest
from _support import FakeLogger
from liteyuki.session import MessageEvent, on_message
from liteyuki.session.on import _reset_matchers
from liteyukibot_runtime_v6 import host as v6_host
from liteyukibot_runtime_v6.events import reply_to_message, to_legacy_message_event
from liteyukibot_runtime_v6.host import _V6BridgeHost, load_configured_v6_plugins

from liteyukibot.broker import ActionResult, BrokerBridgeRunner, BrokerDelivery, BrokerEvent, EventMessage
from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope, Message, Segment


@pytest.fixture(autouse=True)
def reset_matchers() -> Iterator[None]:
    _reset_matchers()
    yield
    _reset_matchers()


def _envelope(*, message: Message | None = None, runtime_id: str = "adapter") -> EventEnvelope:
    return EventEnvelope(
        id="event-1",
        runtime_id=runtime_id,
        adapter="onebot-v11",
        bot_id="bot-1",
        type="message.group.normal",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=ActorRef(id="user-1"),
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


def _delivery(payload: dict[str, Any]) -> BrokerDelivery:
    event = BrokerEvent(
        kernel_event_id="kernel-event-1",
        source_bridge_id="adapter",
        source_event_id="event-1",
        topic="onebot.v11.message.group",
        ordering_key="bot-1:group:group-1",
        payload=payload,
    )
    message = EventMessage(
        delivery_id="delivery-1",
        lease_id="lease-1",
        lease_ttl_ms=5_000,
        event=event,
    )
    return BrokerDelivery(cast(BrokerBridgeRunner, _FakeRunner([])), message)


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
    event.data["nested"]["value"] = 2
    assert envelope.model_dump(mode="json")["raw"] == {"nested": {"value": 1}}


def test_reply_intents_translate_to_portable_messages() -> None:
    text = reply_to_message("hello")
    mention = reply_to_message({"type": "mention", "data": {"user_id": "user-2"}})
    image = reply_to_message({"type": "image", "data": {"url": "https://example.invalid/image.png"}})

    assert text.plain_text == "hello"
    assert mention.segments[0] == Segment(type="mention", data={"user_id": "user-2"})
    assert image.segments[0] == Segment(
        type="adapter",
        data={"type": "image", "data": {"url": "https://example.invalid/image.png"}},
    )
    with pytest.raises(ValueError, match="non-empty string type"):
        reply_to_message({"data": {}})
    with pytest.raises(ValueError, match="object data field"):
        reply_to_message({"type": "text", "data": "invalid"})


def test_v6_loader_imports_only_configured_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    class Entry:
        def __init__(self, name: str) -> None:
            self.name = name
            self.loaded = False

        def load(self) -> object:
            self.loaded = True
            return object()

    selected = Entry("selected")
    ignored = Entry("ignored")
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda **_kwargs: (selected, ignored))

    assert load_configured_v6_plugins(["selected"]) == ("selected",)
    assert selected.loaded is True
    assert ignored.loaded is False


def test_v6_loader_rejects_legacy_options_and_generation_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="migration_required"):
        v6_host._reject_legacy_options({"plugins": ["legacy.module"]})
    monkeypatch.setenv("LITEYUKI_RUNTIME_GENERATION_DIR", "generation")
    with pytest.raises(RuntimeError, match="migration_required"):
        v6_host._reject_legacy_options({})


class _FakeRunner:
    def __init__(self, outcomes: list[bool]) -> None:
        self.outcomes = list(outcomes)
        self.actions: list[dict[str, Any]] = []

    async def request_action(self, **request: Any) -> ActionResult:
        self.actions.append(request)
        return ActionResult(
            action_id=f"action-{len(self.actions)}",
            success=self.outcomes.pop(0) if self.outcomes else True,
            payload=None,
        )

    async def serve_forever(self) -> None:
        await asyncio.Event().wait()


def _broker_delivery(runner: _FakeRunner, payload: dict[str, Any]) -> BrokerDelivery:
    broker_event = BrokerEvent(
        kernel_event_id="kernel-event-1",
        source_bridge_id="adapter",
        source_event_id="event-1",
        topic="onebot.v11.message.group",
        ordering_key="bot-1:group:group-1",
        payload=payload,
    )
    return BrokerDelivery(
        cast(BrokerBridgeRunner, runner),
        EventMessage(
            delivery_id="delivery-1",
            lease_id="lease-1",
            lease_ttl_ms=5_000,
            event=broker_event,
        ),
    )


@pytest.mark.asyncio
async def test_v6_bridge_preserves_reply_order_and_isolates_action_failure() -> None:
    matcher = on_message()

    @matcher.handle()
    async def reply(event: MessageEvent) -> None:
        event.reply("first")
        event.reply({"type": "text", "data": {"text": "second"}})

    runner = _FakeRunner([False, True])
    host = _V6BridgeHost(
        cast(BrokerBridgeRunner, runner),
        "v6",
        FakeLogger(),
        max_concurrent_events=2,
        restart_requested=asyncio.Event(),
    )

    await host.handle_delivery(_broker_delivery(runner, _envelope().model_dump(mode="json")))

    assert len(runner.actions) == 2
    assert [action["payload"]["message"]["segments"][0]["data"]["text"] for action in runner.actions] == [
        "first",
        "second",
    ]
    assert all(action["kind"] == "message.send" for action in runner.actions)
    assert all(action["resource_key"] == "bot:adapter:bot-1" for action in runner.actions)


@pytest.mark.asyncio
async def test_v6_bridge_rejects_malformed_event_and_ignores_non_message() -> None:
    runner = _FakeRunner([])
    host = _V6BridgeHost(
        cast(BrokerBridgeRunner, runner),
        "v6",
        FakeLogger(),
        max_concurrent_events=1,
        restart_requested=asyncio.Event(),
    )
    non_message = _envelope(message=None).model_dump(mode="json")
    non_message["message"] = None

    await host.handle_delivery(_broker_delivery(runner, non_message))
    assert runner.actions == []
    with pytest.raises(ValueError):
        await host.handle_delivery(_broker_delivery(runner, {"invalid": True}))


@pytest.mark.asyncio
async def test_v6_bridge_restart_wait_returns_without_broker_supervision() -> None:
    runner = _FakeRunner([])
    restart = asyncio.Event()
    restart.set()
    host = _V6BridgeHost(
        cast(BrokerBridgeRunner, runner),
        "v6",
        FakeLogger(),
        max_concurrent_events=1,
        restart_requested=restart,
    )

    assert await host.serve() == "restart"
