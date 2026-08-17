from __future__ import annotations

import asyncio

import pytest
from liteyukibot_cordis import (
    CordisAuditService,
    CordisManager,
    CordisSession,
    ProviderCycleError,
    Scope,
    UnavailableProviderError,
)

from liteyukibot.events import (
    ActionEnvelope,
    ActionResult,
    ConversationRef,
    EventBus,
    EventEnvelope,
    Message,
    Segment,
    SendMessage,
)


class RecordingActions:
    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        del action, event
        raise AssertionError("this test only uses emitted actions")


class ExecutingActions:
    def __init__(self) -> None:
        self.calls: list[ActionEnvelope] = []

    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        assert event is not None
        self.calls.append(action)
        return ActionResult(action_id=action.action_id, success=True)


def event() -> EventEnvelope:
    return EventEnvelope(
        runtime_id="test",
        adapter="test",
        bot_id="bot",
        type="message",
        conversation=ConversationRef(id="conversation"),
    )


def action(source: EventEnvelope, text: str) -> ActionEnvelope:
    return ActionEnvelope(
        runtime_id=source.runtime_id,
        bot_id=source.bot_id,
        action=SendMessage(
            message=Message(segments=(Segment(type="text", data={"text": text}),)),
            conversation=source.conversation,
        ),
    )


@pytest.mark.asyncio
async def test_scope_lazily_resolves_ancestor_provider_and_closes_in_reverse_order() -> None:
    closed: list[str] = []
    root = Scope(plugin_id="root")
    child = root.child(plugin_id="plugin")

    class Resource:
        async def aclose(self) -> None:
            closed.append("resource")

    root.provide("resource", lambda: Resource())
    root.own(lambda: closed.append("root"))
    assert await child.use("resource") is await root.use("resource")

    await root.aclose()

    assert closed == ["resource", "root"]
    assert child.closed
    assert root._children == []  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_scope_rejects_missing_and_cycles() -> None:
    scope = Scope(plugin_id="plugin")
    with pytest.raises(UnavailableProviderError):
        await scope.use("missing")

    async def left(current: Scope) -> object:
        return await current.use("right")

    async def right(current: Scope) -> object:
        return await current.use("left")

    scope.provide("left", left)
    scope.provide("right", right)
    with pytest.raises(ProviderCycleError, match="left.*right.*left"):
        await scope.use("left")


@pytest.mark.asyncio
async def test_manager_composes_presets_and_preserves_envelope_identity() -> None:
    seen: list[str] = []
    bus = EventBus()
    manager = CordisManager(bus, RecordingActions())
    source = event()

    async def factory(scope: Scope) -> None:
        async def first(session: CordisSession) -> None:
            seen.append("first")
            assert session.event.envelope is source

        async def failing(_session: object) -> None:
            seen.append("failure")
            raise RuntimeError("stop ordered only")

        async def skipped(_session: object) -> None:
            seen.append("skipped")

        async def left(_session: object) -> None:
            await asyncio.sleep(0)
            seen.append("parallel-left")

        async def right(_session: object) -> None:
            seen.append("parallel-right")

        async def middleware(session: object, next_stage: object) -> None:
            seen.append("before")
            await next_stage()  # type: ignore[operator]
            seen.append("after")

        async def terminal(_session: object, _next_stage: object) -> None:
            seen.append("terminal")

        scope.on(first, order=1)
        scope.on(failing, order=2)
        scope.on(skipped, order=3)
        scope.parallel(left)
        scope.parallel(right)
        scope.middleware(middleware)
        scope.middleware(terminal)
        scope.route(
            "message",
            lambda current: current.envelope.type == "message",
            lambda _session: seen.append("route"),
        )
        scope.route("other", lambda _current: False, lambda _session: seen.append("wrong-route"))

    await manager.activate("example.plugin", factory)
    result = await manager.dispatch(source)

    assert seen == ["first", "failure", "parallel-right", "parallel-left", "before", "terminal", "after", "route"]
    assert result.failures == ("ordered: RuntimeError",)
    assert any(record.operation == "ordered" and record.outcome == "error" for record in manager.audit.snapshot())
    await manager.aclose()


@pytest.mark.asyncio
async def test_manager_subscribes_once_and_audit_is_bounded() -> None:
    audit = CordisAuditService(capacity=2)
    bus = EventBus()
    manager = CordisManager(bus, RecordingActions(), audit=audit)
    await manager.start()
    await manager.start()
    assert len(bus._handlers) == 1  # pyright: ignore[reportPrivateUsage]

    audit.record(plugin_id="a", scope_id="s", event_id="1", operation="one", outcome="ok")
    audit.record(plugin_id="a", scope_id="s", event_id="2", operation="two", outcome="ok")
    audit.record(plugin_id="a", scope_id="s", event_id="3", operation="three", outcome="ok")
    assert tuple(record.event_id for record in audit.snapshot()) == ("2", "3")
    assert audit.snapshot(limit=0) == ()
    await manager.aclose()


@pytest.mark.asyncio
async def test_parallel_actions_are_merged_by_registration_order() -> None:
    source = event()
    manager = CordisManager(EventBus(), RecordingActions())

    async def factory(scope: Scope) -> None:
        async def first(session: CordisSession) -> None:
            await asyncio.sleep(0.01)
            session.emit(action(source, "first"))

        async def second(session: CordisSession) -> None:
            session.emit(action(source, "second"))

        scope.parallel(first)
        scope.parallel(second)

    await manager.activate("example.plugin", factory)
    result = await manager.dispatch(source)

    texts: list[str] = []
    for item in result.actions:
        assert isinstance(item.action, SendMessage)
        texts.append(item.action.message.plain_text)
    assert texts == ["first", "second"]
    await manager.aclose()


@pytest.mark.asyncio
async def test_session_execute_is_not_returned_for_event_bus_reexecution() -> None:
    source = event()
    actions = ExecutingActions()
    manager = CordisManager(EventBus(), actions)

    async def factory(scope: Scope) -> None:
        async def handler(session: CordisSession) -> None:
            result = await session.execute(action(source, "direct"))
            assert result.success

        scope.on(handler)

    await manager.activate("example.plugin", factory)
    result = await manager.dispatch(source)

    assert result.actions == ()
    assert len(result.action_results) == 1
    assert len(actions.calls) == 1
    await manager.aclose()


@pytest.mark.asyncio
async def test_scheduler_is_cancelled_when_its_plugin_scope_closes() -> None:
    source = event()
    manager = CordisManager(EventBus(), RecordingActions())
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def factory(scope: Scope) -> None:
        async def scheduler(_event: object, work: tuple[object, ...]) -> None:
            assert work
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        scope.on(lambda _session: None)
        scope.schedule(scheduler)

    await manager.activate("example.plugin", factory)
    await manager.dispatch(source)
    await asyncio.wait_for(started.wait(), timeout=1)
    await manager.aclose()

    assert cancelled.is_set()
    assert manager.scope._children == []  # pyright: ignore[reportPrivateUsage]
