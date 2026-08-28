"""Minimal Cordis event composition over the protocol-neutral kernel."""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, cast

from liteyukibot_kernel.events import (
    ActionEnvelope,
    ActionResult,
    EventBus,
    EventEnvelope,
    HandlerFailure,
    HandlerResult,
    Subscription,
)

from .scope import Disposer, RegistrationSink, Scope

type OrderedHandler = Callable[[CordisSession], Awaitable[None] | None]
type PluginFactory = Callable[[Scope], Awaitable[None] | None]


class ActionServiceLike(Protocol):
    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        """Execute one action through the host action service."""
        ...


@dataclass(frozen=True, slots=True)
class CordisEvent:
    """A view over the original kernel event; no second event identity is minted."""

    envelope: EventEnvelope

    @property
    def raw(self) -> EventEnvelope:
        return self.envelope


@dataclass(slots=True)
class CordisSession:
    """Per-event session exposing scoped dependencies and action dispatch."""

    event: CordisEvent
    scope: Scope
    actions: ActionServiceLike
    _emitted: list[ActionEnvelope] = field(default_factory=list)
    _action_results: list[ActionResult] = field(default_factory=list)

    def emit(self, action: ActionEnvelope) -> None:
        """Queue an action for EventBus execution after ordered handlers complete."""
        self._emitted.append(self._bind(action))

    async def execute(self, action: ActionEnvelope) -> ActionResult:
        """Execute an action directly and retain its correlated result."""
        bound = self._bind(action)
        result = await self.actions.execute(bound, event=self.event.envelope)
        self._action_results.append(result)
        return result

    def _bind(self, action: ActionEnvelope) -> ActionEnvelope:
        event = self.event.envelope
        if action.event_id not in (None, event.id):
            raise ValueError("Cordis action event_id must match the wrapped event")
        if action.event_id is None:
            action = action.model_copy(update={"event_id": event.id})
        if action.runtime_id != event.runtime_id or action.bot_id != event.bot_id:
            raise ValueError("Cordis action target must match the wrapped event")
        return action


@dataclass(frozen=True, slots=True)
class CordisDispatchResult:
    actions: tuple[ActionEnvelope, ...]
    failures: tuple[str, ...]
    action_results: tuple[ActionResult, ...] = ()


@dataclass(frozen=True, slots=True)
class _Registration:
    scope: Scope
    order: int
    handler: OrderedHandler
    sequence: int


class CordisManager(RegistrationSink):
    """Compose trusted in-process plugins on one deterministic ordered chain."""

    def __init__(self, events: EventBus, actions: ActionServiceLike) -> None:
        self.events = events
        self.actions = actions
        self.scope = Scope(plugin_id="liteyukibot.cordis", sink=self)
        self._registrations: list[_Registration] = []
        self._plugin_scopes: dict[str, Scope] = {}
        self._sequence = 0
        self._subscription: Subscription | None = None
        self._closed = False

    @property
    def active_plugin_ids(self) -> tuple[str, ...]:
        return tuple(self._plugin_scopes)

    async def activate(
        self,
        plugin_id: str,
        factory: PluginFactory,
        *,
        config: Mapping[str, object] | None = None,
        parent: Scope | None = None,
    ) -> Scope:
        if self._closed:
            raise RuntimeError("Cordis manager is closed")
        if plugin_id in self._plugin_scopes:
            raise ValueError(f"Cordis plugin {plugin_id!r} is already activated")
        scope = (parent or self.scope).child(plugin_id=plugin_id, config=config)
        try:
            result = factory(scope)
            if inspect.isawaitable(result):
                await result
        except BaseException:
            await scope.aclose()
            raise
        self._plugin_scopes[plugin_id] = scope
        return scope

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("Cordis manager is closed")
        if self._subscription is None:
            self._subscription = self.events.subscribe(self._handle_event, name="cordis.manager")

    def register(self, scope: Scope, order: int, handler: object) -> Disposer:
        if self._closed:
            raise RuntimeError("Cordis manager is closed")
        if not callable(handler):
            raise TypeError("Cordis event handler must be callable")
        registration = _Registration(scope, order, cast(OrderedHandler, handler), self._sequence)
        self._sequence += 1
        self._registrations.append(registration)

        def dispose() -> None:
            with contextlib.suppress(ValueError):
                self._registrations.remove(registration)

        return dispose

    async def dispatch(self, envelope: EventEnvelope) -> CordisDispatchResult:
        # Built-in features form an ancestor-linked activation chain. Starting
        # the event scope beneath the newest feature exposes that dependency
        # chain to handlers while keeping event-owned resources short-lived.
        parent = next(reversed(self._plugin_scopes.values()), self.scope)
        event_scope = parent.child(plugin_id="event")
        session = CordisSession(CordisEvent(envelope), event_scope, self.actions)
        failures: list[str] = []
        try:
            ordered = sorted(self._registrations, key=lambda item: (item.order, item.sequence))
            for item in ordered:
                try:
                    result = item.handler(session)
                    if inspect.isawaitable(result):
                        await result
                except Exception as error:
                    failures.append(f"ordered: {type(error).__name__}")
                    break
            return CordisDispatchResult(tuple(session._emitted), tuple(failures), tuple(session._action_results))
        finally:
            await event_scope.aclose()

    async def _handle_event(self, envelope: EventEnvelope) -> HandlerResult:
        result = await self.dispatch(envelope)
        failures = tuple(
            HandlerFailure(handler="cordis.manager", kind="error", message=failure) for failure in result.failures
        )
        return HandlerResult(actions=result.actions, action_results=result.action_results, failures=failures)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._subscription is not None:
            self.events.unsubscribe(self._subscription)
            self._subscription = None
        self._registrations.clear()
        try:
            await self.scope.aclose()
        finally:
            self._plugin_scopes.clear()


__all__ = [
    "ActionServiceLike",
    "CordisDispatchResult",
    "CordisEvent",
    "CordisManager",
    "CordisSession",
    "OrderedHandler",
    "PluginFactory",
]
