from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from liteyukibot.events import (
    ActionEnvelope,
    ActionResult,
    ActorRef,
    CallApi,
    ConversationRef,
    EventBus,
    EventEnvelope,
    HandlerResult,
    Message,
    Segment,
    SendMessage,
)


def event(event_id: str, conversation_id: str = "conversation") -> EventEnvelope:
    return EventEnvelope(
        id=event_id,
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="message.created",
        conversation=ConversationRef(id=conversation_id, type="group"),
        actor=ActorRef(id="user", display_name="User"),
        message=Message(segments=(Segment(type="text", data={"text": event_id}),)),
    )


def test_models_are_frozen_json_safe_and_discriminated() -> None:
    source = event("event-1")
    assert source.message is not None
    assert source.message.plain_text == "event-1"
    assert source.ordering_key == ("runtime", "bot", "group:conversation")
    assert EventEnvelope.model_validate_json(source.model_dump_json()) == source

    with pytest.raises(ValidationError):
        source.bot_id = "other"
    with pytest.raises(TypeError):
        source.raw["changed"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        source.message.segments[0].data["text"] = "changed"  # type: ignore[index]
    with pytest.raises(ValidationError, match="non-JSON"):
        EventEnvelope(
            runtime_id="runtime",
            adapter="test",
            bot_id="bot",
            type="event",
            conversation=ConversationRef(id="conversation"),
            raw=cast(Any, {"bad": object()}),
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        EventEnvelope(
            timestamp=datetime(2026, 1, 1),
            runtime_id="runtime",
            adapter="test",
            bot_id="bot",
            type="event",
            conversation=ConversationRef(id="conversation"),
        )

    send = ActionEnvelope(
        action_id="action-send",
        event_id=source.id,
        runtime_id=source.runtime_id,
        bot_id=source.bot_id,
        action=SendMessage(message=source.message, reply_token="reply-token"),
    )
    call = ActionEnvelope.model_validate(
        {
            "action_id": "action-call",
            "runtime_id": "runtime",
            "bot_id": "bot",
            "action": {"type": "call_api", "api": "get_status", "params": {"verbose": True}},
        }
    )
    assert isinstance(send.action, SendMessage)
    assert isinstance(call.action, CallApi)
    assert call.model_dump(mode="json")["action"]["type"] == "call_api"


def test_handler_order_stop_propagation_and_action_execution() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        executed: list[str] = []
        action = ActionEnvelope(
            action_id="action",
            event_id="event",
            runtime_id="runtime",
            bot_id="bot",
            action=CallApi(api="test"),
        )

        async def execute(envelope: ActionEnvelope) -> ActionResult:
            executed.append(envelope.action_id)
            return ActionResult(action_id=envelope.action_id, success=True, data={"ok": True})

        async def first(_event: EventEnvelope) -> None:
            calls.append("first")

        async def second(_event: EventEnvelope) -> HandlerResult:
            calls.append("second")
            return HandlerResult(actions=(action,), stop_propagation=True)

        async def last(_event: EventEnvelope) -> None:
            calls.append("last")

        async with EventBus(action_executor=execute) as bus:
            bus.subscribe(last, order=10)
            bus.subscribe(first, order=0)
            bus.subscribe(second, order=0)
            result = await bus.publish(event("event"))

        assert calls == ["first", "second"]
        assert executed == ["action"]
        assert result.status == "processed"
        assert result.handlers_called == 2
        assert result.stopped is True
        assert result.action_results[0].success is True

    asyncio.run(scenario())


def test_per_conversation_order_and_cross_conversation_concurrency() -> None:
    async def scenario() -> None:
        same_key_timeline: list[str] = []

        async def ordered_handler(current: EventEnvelope) -> None:
            same_key_timeline.append(f"start:{current.id}")
            await asyncio.sleep(0.01)
            same_key_timeline.append(f"end:{current.id}")

        async with EventBus(max_concurrent_events=2) as bus:
            bus.subscribe(ordered_handler)
            first = asyncio.create_task(bus.publish(event("one")))
            await asyncio.sleep(0)
            second = asyncio.create_task(bus.publish(event("two")))
            await asyncio.gather(first, second)

        assert same_key_timeline == ["start:one", "end:one", "start:two", "end:two"]

        both_started = asyncio.Event()
        started: set[str] = set()

        async def concurrent_handler(current: EventEnvelope) -> None:
            started.add(current.id)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.2)

        async with EventBus(max_concurrent_events=2) as bus:
            bus.subscribe(concurrent_handler)
            await asyncio.gather(
                bus.publish(event("left", "left-conversation")),
                bus.publish(event("right", "right-conversation")),
            )
        assert started == {"left", "right"}

    asyncio.run(scenario())


def test_handler_timeout_and_error_are_isolated() -> None:
    async def scenario() -> None:
        called: list[str] = []

        async def broken(_event: EventEnvelope) -> None:
            raise RuntimeError("broken")

        async def slow(_event: EventEnvelope) -> None:
            await asyncio.sleep(1)

        async def healthy(_event: EventEnvelope) -> None:
            called.append("healthy")

        async with EventBus(handler_timeout=0.01) as bus:
            bus.subscribe(broken, name="broken")
            bus.subscribe(slow, name="slow")
            bus.subscribe(healthy, name="healthy")
            result = await bus.publish(event("event"))

        assert called == ["healthy"]
        assert result.status == "processed"
        assert [(failure.handler, failure.kind) for failure in result.failures] == [
            ("broken", "error"),
            ("slow", "timeout"),
        ]

    asyncio.run(scenario())


def test_overload_is_an_explicit_result() -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        async def blocking(_event: EventEnvelope) -> None:
            entered.set()
            await release.wait()

        bus = EventBus(queue_capacity=1, enqueue_timeout=0)
        async with bus:
            bus.subscribe(blocking)
            first = asyncio.create_task(bus.publish(event("first")))
            await entered.wait()
            overloaded = await bus.publish(event("second", "other"))
            release.set()
            processed = await first

        assert overloaded.status == "overloaded"
        assert processed.status == "processed"
        assert (await bus.publish(event("after-close"))).status == "closed"

    asyncio.run(scenario())
