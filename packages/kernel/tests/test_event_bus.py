from __future__ import annotations

import asyncio
import math
from typing import Any, cast

import pytest
from liteyukibot_kernel import (
    ActionEnvelope,
    ActionResult,
    ActionService,
    ConversationRef,
    EventBus,
    EventEnvelope,
    HandlerFailure,
    HandlerResult,
    Message,
    Segment,
    SendMessage,
)
from liteyukibot_kernel.tasks import ManagedTasks


def _event() -> EventEnvelope:
    return EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="message",
        conversation=ConversationRef(id="conversation", type="private"),
    )


class _RecordingLogger:
    def __init__(self) -> None:
        self.records: list[object] = []

    def bind(self, **_values: object) -> _RecordingLogger:
        return self

    def error(self, template: str, *args: object, **_values: object) -> None:
        self.records.append((template, args))

    def warning(self, template: str, *args: object, **_values: object) -> None:
        self.records.append((template, args))


@pytest.mark.asyncio
async def test_event_bus_preserves_reported_handler_outcomes() -> None:
    failure = HandlerFailure(handler="test.handler", kind="error", message="boom")
    action_result = ActionResult(action_id="action", success=True)
    bus = EventBus()

    async def handler(_event: EventEnvelope) -> HandlerResult:
        return HandlerResult(
            action_results=(action_result,),
            failures=(failure,),
        )

    bus.subscribe(handler)

    result = await bus.publish(_event())

    assert result.failures == (failure,)
    assert result.action_results == (action_result,)
    await bus.aclose()


def test_event_bus_rejects_a_subscription_from_another_bus() -> None:
    first = EventBus()
    second = EventBus()

    async def handler(_event: EventEnvelope) -> None:
        return None

    first_subscription = first.subscribe(handler)
    foreign_subscription = second.subscribe(handler)

    assert first.unsubscribe(foreign_subscription) is False
    assert first.unsubscribe(first_subscription) is True


def test_event_bus_rejects_synchronous_callbacks() -> None:
    bus = EventBus()
    with pytest.raises(TypeError, match="async callables"):
        bus.subscribe(cast(Any, lambda _event: None))
    with pytest.raises(TypeError, match="async callable"):
        EventBus(action_executor=cast(Any, lambda _event, _action: ActionResult(action_id="x", success=True)))


def test_event_bus_rejects_non_finite_timeouts() -> None:
    for field in ("enqueue_timeout", "handler_timeout", "action_timeout", "close_timeout"):
        with pytest.raises(ValueError, match="finite"):
            EventBus(**cast(Any, {field: math.inf}))
        with pytest.raises(ValueError, match="finite"):
            EventBus(**cast(Any, {field: math.nan}))


def test_managed_tasks_rejects_invalid_stop_timeout() -> None:
    tasks = ManagedTasks("test")
    for value in (math.inf, math.nan, -1.0):
        with pytest.raises(ValueError, match="finite"):
            asyncio.run(tasks.stop(value))


def test_event_bus_rejects_invalid_event_byte_budget() -> None:
    with pytest.raises(ValueError, match="max_event_bytes"):
        EventBus(max_event_bytes=0)


def test_action_service_rejects_synchronous_callbacks() -> None:
    async def backend(_event: EventEnvelope | None, action: ActionEnvelope) -> ActionResult:
        return ActionResult(action_id=action.action_id, success=True)

    with pytest.raises(TypeError, match="action backend"):
        ActionService(cast(Any, lambda _event, _action: ActionResult(action_id="x", success=True)), backend)
    with pytest.raises(TypeError, match="action policy"):
        ActionService(backend, cast(Any, lambda _event, _action: None))


def _action(event: EventEnvelope) -> ActionEnvelope:
    return ActionEnvelope(
        event_id=event.id,
        runtime_id=event.runtime_id,
        bot_id=event.bot_id,
        action=SendMessage(
            conversation=event.conversation,
            message=Message(segments=(Segment(type="text", data={"text": "reply"}),)),
        ),
    )


@pytest.mark.asyncio
async def test_event_bus_bounds_action_execution() -> None:
    async def execute(_event: EventEnvelope, _action: ActionEnvelope) -> ActionResult:
        await asyncio.sleep(10)
        return ActionResult(action_id=_action.action_id, success=True)

    bus = EventBus(action_timeout=0.01, action_executor=execute)

    async def handler(event: EventEnvelope) -> HandlerResult:
        return HandlerResult(actions=(_action(event),))

    bus.subscribe(handler)

    result = await bus.publish(_event())

    assert result.status == "processed"
    assert result.action_results[0].error_code == "ACTION_TIMEOUT"
    await bus.aclose()


@pytest.mark.asyncio
async def test_event_bus_blocks_actions_after_an_uncooperative_action_timeout() -> None:
    source = _event()
    first = _action(source)
    second = _action(source)
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release = asyncio.Event()

    async def execute(_event: EventEnvelope, action: ActionEnvelope) -> ActionResult:
        if action.action_id == first.action_id:
            first_started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
        else:
            second_started.set()
        return ActionResult(action_id=action.action_id, success=True)

    bus = EventBus(action_timeout=0.01, action_executor=execute)

    async def handler(_event: EventEnvelope) -> HandlerResult:
        return HandlerResult(actions=(first, second))

    bus.subscribe(handler)
    published = asyncio.create_task(bus.publish(source))
    await first_started.wait()
    result = await asyncio.wait_for(published, timeout=1)

    assert [item.error_code for item in result.action_results] == ["ACTION_TIMEOUT", "ACTION_BLOCKED"]
    assert not second_started.is_set()
    release.set()
    await asyncio.sleep(0.01)
    await bus.aclose()


@pytest.mark.asyncio
async def test_event_bus_accepts_operation_completed_during_cancellation_grace() -> None:
    async def operation() -> str:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            return "completed"
        raise AssertionError("operation unexpectedly completed before timeout")

    bus = EventBus()

    assert await bus._run_operation(operation(), timeout_seconds=0.01, name="test operation") == "completed"
    await bus.aclose()


@pytest.mark.asyncio
async def test_event_bus_keeps_admission_until_action_barrier_finishes() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def execute(_event: EventEnvelope, _action: ActionEnvelope) -> ActionResult:
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        return ActionResult(action_id=_action.action_id, success=True)

    async def handler(event: EventEnvelope) -> HandlerResult:
        return HandlerResult(actions=(_action(event),))

    bus = EventBus(action_timeout=0.01, close_timeout=1, action_executor=execute)
    bus.subscribe(handler)
    published = asyncio.create_task(bus.publish(_event()))
    await started.wait()

    result = await asyncio.wait_for(published, timeout=1)
    assert result.action_results[0].error_code == "ACTION_TIMEOUT"
    assert bus.outstanding == 1

    closing = asyncio.create_task(bus.aclose())
    await asyncio.sleep(0.01)
    assert not closing.done()
    release.set()
    await asyncio.wait_for(closing, timeout=1)
    assert bus.outstanding == 0


@pytest.mark.asyncio
async def test_event_bus_blocks_actions_across_handlers_after_an_uncooperative_timeout() -> None:
    source = _event()
    first = _action(source)
    second = _action(source)
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release = asyncio.Event()

    async def execute(_event: EventEnvelope, action: ActionEnvelope) -> ActionResult:
        if action.action_id == first.action_id:
            first_started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
        else:
            second_started.set()
        return ActionResult(action_id=action.action_id, success=True)

    bus = EventBus(action_timeout=0.01, action_executor=execute)

    async def first_handler(_event: EventEnvelope) -> HandlerResult:
        return HandlerResult(actions=(first,))

    async def second_handler(_event: EventEnvelope) -> HandlerResult:
        return HandlerResult(actions=(second,))

    bus.subscribe(first_handler)
    bus.subscribe(second_handler)
    published = asyncio.create_task(bus.publish(source))
    await first_started.wait()
    result = await asyncio.wait_for(published, timeout=1)

    assert [item.error_code for item in result.action_results] == ["ACTION_TIMEOUT", "ACTION_BLOCKED"]
    assert not second_started.is_set()
    release.set()
    await asyncio.sleep(0.01)
    await bus.aclose()


@pytest.mark.asyncio
async def test_event_bus_rejects_events_over_the_byte_budget() -> None:
    bus = EventBus(max_event_bytes=256)
    event = _event().model_copy(update={"raw": {"payload": "x" * 1024}})

    result = await bus.publish(event)

    assert result.status == "overloaded"
    assert bus.outstanding == 0
    await bus.aclose()


@pytest.mark.asyncio
async def test_event_bus_consumes_exception_from_cancellation_grace() -> None:
    loop = asyncio.get_running_loop()
    loop_errors: list[dict[str, object]] = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: loop_errors.append(context))

    async def handler(_event: EventEnvelope) -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError as error:
            raise RuntimeError("late handler failure") from error

    bus = EventBus(handler_timeout=0.01)
    bus.subscribe(handler)
    try:
        result = await bus.publish(_event())
        assert result.failures[0].kind == "timeout"
        await asyncio.sleep(0)
        assert loop_errors == []
    finally:
        await bus.aclose()
        loop.set_exception_handler(previous_handler)


@pytest.mark.asyncio
async def test_event_bus_keeps_same_key_fifo_after_a_timeout() -> None:
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release = asyncio.Event()
    first = _event()
    second = _event()

    async def handler(event: EventEnvelope) -> None:
        if event.id == first.id:
            first_started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
        else:
            second_started.set()

    bus = EventBus(handler_timeout=0.01)
    bus.subscribe(handler)
    first_result = asyncio.create_task(bus.publish(first))
    second_result = asyncio.create_task(bus.publish(second))
    await first_started.wait()

    result = await asyncio.wait_for(first_result, timeout=1)
    assert result.action_results == ()
    assert result.failures[0].kind == "timeout"
    await asyncio.sleep(0.01)
    assert not second_started.is_set()

    release.set()
    await asyncio.wait_for(second_result, timeout=1)
    assert second_started.is_set()
    await bus.aclose()


@pytest.mark.asyncio
async def test_event_bus_closes_queued_events_when_a_key_worker_is_cancelled() -> None:
    first_started = asyncio.Event()
    cancel_first = asyncio.Event()
    first = _event()
    second = _event()

    async def handler(event: EventEnvelope) -> None:
        if event.id == first.id:
            first_started.set()
            await cancel_first.wait()

    bus = EventBus()
    bus.subscribe(handler)
    first_result = asyncio.create_task(bus.publish(first))
    await first_started.wait()
    second_result = asyncio.create_task(bus.publish(second))
    await asyncio.sleep(0)

    worker = next(iter(bus._key_workers.values()))
    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_result
    second_dispatch = await asyncio.wait_for(second_result, timeout=1)

    assert second_dispatch.status == "closed"
    assert bus.outstanding == 0
    await bus.aclose()


@pytest.mark.asyncio
async def test_event_bus_sanitizes_handler_and_action_exceptions() -> None:
    logger = _RecordingLogger()

    async def handler(event: EventEnvelope) -> HandlerResult:
        return HandlerResult(actions=(_action(event),))

    async def execute(_event: EventEnvelope, _action: ActionEnvelope) -> ActionResult:
        raise RuntimeError("token=secret")

    bus = EventBus(action_executor=execute, logger=cast(Any, logger))
    bus.subscribe(handler)
    result = await bus.publish(_event())

    assert "secret" not in str(result)
    assert all("secret" not in str(record) for record in logger.records)
    await bus.aclose()


@pytest.mark.asyncio
async def test_event_bus_force_closes_a_stuck_event_after_deadline() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(_event: EventEnvelope) -> None:
        started.set()
        await release.wait()

    bus = EventBus(close_timeout=0.01)
    bus.subscribe(handler)
    event = _event()
    published = asyncio.create_task(bus.publish(event))
    await started.wait()

    await bus.aclose()

    result = await published
    assert result.event_id == event.id
    assert result.status == "closed"
    assert bus.outstanding == 0
    release.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_event_bus_force_close_resolves_events_waiting_in_a_key_queue() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(_event: EventEnvelope) -> None:
        started.set()
        await release.wait()

    bus = EventBus(queue_capacity=2, close_timeout=0.01)
    bus.subscribe(handler)
    first, second = _event(), _event()
    published = [asyncio.create_task(bus.publish(event)) for event in (first, second)]
    await started.wait()
    await asyncio.sleep(0)

    await bus.aclose()

    results = await asyncio.gather(*published)
    assert [result.status for result in results] == ["closed", "closed"]
    assert bus.outstanding == 0
    release.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_event_bus_tracks_an_uncooperative_handler_after_forced_close() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(_event: EventEnvelope) -> None:
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()

    bus = EventBus(handler_timeout=5, close_timeout=0.01)
    bus.subscribe(handler)
    published = asyncio.create_task(bus.publish(_event()))
    await started.wait()

    await bus.aclose()

    result = await published
    assert result.status == "closed"
    assert bus.outstanding == 0
    assert not bus._key_workers
    assert len(bus._operation_tasks) == 1
    release.set()
    await asyncio.sleep(0.01)
    assert not bus._operation_tasks


@pytest.mark.asyncio
async def test_event_bus_tracks_an_uncooperative_action_after_forced_close() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def execute(_event: EventEnvelope, _action: ActionEnvelope) -> ActionResult:
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        return ActionResult(action_id=_action.action_id, success=True)

    async def handler(event: EventEnvelope) -> HandlerResult:
        return HandlerResult(actions=(_action(event),))

    bus = EventBus(action_timeout=5, close_timeout=0.01, action_executor=execute)
    bus.subscribe(handler)
    published = asyncio.create_task(bus.publish(_event()))
    await started.wait()

    await bus.aclose()

    result = await published
    assert result.status == "closed"
    assert bus.outstanding == 0
    assert not bus._key_workers
    assert len(bus._operation_tasks) == 1
    release.set()
    await asyncio.sleep(0.01)
    assert not bus._operation_tasks
