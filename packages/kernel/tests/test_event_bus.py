from __future__ import annotations

import pytest
from liteyukibot_kernel import (
    ActionResult,
    ConversationRef,
    EventBus,
    EventEnvelope,
    HandlerFailure,
    HandlerResult,
)


def _event() -> EventEnvelope:
    return EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="message",
        conversation=ConversationRef(id="conversation", type="private"),
    )


@pytest.mark.asyncio
async def test_event_bus_preserves_reported_handler_outcomes() -> None:
    failure = HandlerFailure(handler="test.handler", kind="error", message="boom")
    action_result = ActionResult(action_id="action", success=True)
    bus = EventBus()
    bus.subscribe(
        lambda _event: HandlerResult(
            action_results=(action_result,),
            failures=(failure,),
        )
    )

    result = await bus.publish(_event())

    assert result.failures == (failure,)
    assert result.action_results == (action_result,)
    await bus.aclose()


def test_event_bus_rejects_a_subscription_from_another_bus() -> None:
    first = EventBus()
    second = EventBus()
    first_subscription = first.subscribe(lambda _event: None)
    foreign_subscription = second.subscribe(lambda _event: None)

    assert first.unsubscribe(foreign_subscription) is False
    assert first.unsubscribe(first_subscription) is True
