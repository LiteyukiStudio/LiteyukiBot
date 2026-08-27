from __future__ import annotations

import asyncio

import pytest
from liteyukibot_cordis import (
    CordisManager,
    CordisSession,
    ProviderCycleError,
    Scope,
    UnavailableProviderError,
    discover_plugins,
)
from liteyukibot_kernel.events import (
    ActionEnvelope,
    ActionResult,
    ConversationRef,
    EventBus,
    EventEnvelope,
    Message,
    Segment,
    SendMessage,
)


class _Actions:
    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        assert event is not None
        return ActionResult(action_id=action.action_id, success=True)


def _event() -> EventEnvelope:
    return EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="message",
        conversation=ConversationRef(id="conversation", type="private"),
    )


@pytest.mark.asyncio
async def test_scope_resolves_ancestor_and_closes_in_reverse_order() -> None:
    closed: list[str] = []
    root = Scope(plugin_id="root")
    child = root.child(plugin_id="child")

    class Resource:
        async def aclose(self) -> None:
            closed.append("resource")

    root.provide("resource", Resource)
    root.own(lambda: closed.append("root"))
    assert await child.use("resource") is await root.use("resource")
    await root.aclose()
    assert closed == ["resource", "root"]
    assert child.closed


@pytest.mark.asyncio
async def test_scope_rejects_missing_and_cyclic_providers() -> None:
    scope = Scope(plugin_id="test")
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
async def test_manager_runs_ordered_handlers_and_binds_emitted_actions() -> None:
    manager = CordisManager(EventBus(), _Actions())
    seen: list[str] = []

    async def factory(scope: Scope) -> None:
        async def first(session: CordisSession) -> None:
            seen.append("first")
            source = session.event.envelope
            session.emit(
                ActionEnvelope(
                    runtime_id=source.runtime_id,
                    bot_id=source.bot_id,
                    action=SendMessage(
                        message=Message(segments=(Segment(type="text", data={"text": "ok"}),)),
                        conversation=source.conversation,
                    ),
                )
            )

        async def second(_session: CordisSession) -> None:
            await asyncio.sleep(0)
            seen.append("second")

        scope.on(second, order=2)
        scope.on(first, order=1)

    await manager.activate("test", factory)
    source = _event()
    result = await manager.dispatch(source)
    assert seen == ["first", "second"]
    assert result.failures == ()
    assert result.actions[0].event_id == source.id
    await manager.aclose()


def test_discovery_loads_only_explicit_plugins_in_configuration_order(monkeypatch: pytest.MonkeyPatch) -> None:
    async def first(_scope: Scope) -> None:
        return None

    async def second(_scope: Scope) -> None:
        return None

    class EntryPoint:
        def __init__(self, name: str, factory: object) -> None:
            self.name = name
            self._factory = factory

        def load(self) -> object:
            return self._factory

    entries = (EntryPoint("second", second), EntryPoint("unused", object()), EntryPoint("first", first))
    monkeypatch.setattr("liteyukibot_cordis.discovery.metadata.entry_points", lambda *, group: entries)

    assert discover_plugins(("first", "second")) == (("first", first), ("second", second))
    with pytest.raises(RuntimeError, match="not installed"):
        discover_plugins(("missing",))
