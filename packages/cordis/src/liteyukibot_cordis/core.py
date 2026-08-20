"""Cordis event facade, composition manager, and EventBus host adapter."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from time import monotonic
from typing import Protocol, cast

from liteyukibot.events import ActionEnvelope, ActionResult, EventBus, EventEnvelope, HandlerResult, Subscription

from .audit import CordisAuditService
from .scope import Disposer, RegistrationSink, Scope

type OrderedHandler = Callable[[CordisSession], Awaitable[None] | None]
type ParallelHandler = OrderedHandler
type WaterfallHandler = Callable[[CordisSession, Callable[[], Awaitable[None]]], Awaitable[None] | None]
type RoutePredicate = Callable[[CordisEvent], bool | Awaitable[bool]]
type Scheduler = Callable[[CordisEvent, tuple[object, ...]], Awaitable[None] | None]
type PluginFactory = Callable[[Scope], Awaitable[None] | None]


class ActionServiceLike(Protocol):
    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult: ...


@dataclass(frozen=True, slots=True)
class CordisEvent:
    envelope: EventEnvelope

    @property
    def raw(self) -> EventEnvelope:
        return self.envelope


@dataclass(slots=True)
class CordisSession:
    event: CordisEvent
    scope: Scope
    actions: ActionServiceLike
    _emitted: list[ActionEnvelope] = field(default_factory=list)
    _action_results: list[ActionResult] = field(default_factory=list)

    def emit(self, action: ActionEnvelope) -> None:
        self._emitted.append(self._bind(action))

    async def execute(self, action: ActionEnvelope) -> ActionResult:
        action = self._bind(action)
        result = await self.actions.execute(action, event=self.event.envelope)
        self._action_results.append(result)
        return result

    def _bind(self, action: ActionEnvelope) -> ActionEnvelope:
        if action.event_id not in (None, self.event.envelope.id):
            raise ValueError("Cordis action event_id must match the wrapped event")
        if action.event_id is None:
            return action.model_copy(update={"event_id": self.event.envelope.id})
        return action


@dataclass(frozen=True, slots=True)
class CordisDispatchResult:
    actions: tuple[ActionEnvelope, ...]
    failures: tuple[str, ...]
    action_results: tuple[ActionResult, ...] = ()


@dataclass(frozen=True, slots=True)
class _Registration:
    scope: Scope
    kind: str
    value: object
    sequence: int


class CordisManager(RegistrationSink):
    """One EventBus subscriber that composes Cordis plugin registrations."""

    def __init__(
        self, events: EventBus, actions: ActionServiceLike, *, audit: CordisAuditService | None = None
    ) -> None:
        self.events = events
        self.actions = actions
        self.audit = audit or CordisAuditService()
        self.scope = Scope(plugin_id="liteyukibot.cordis", sink=self, audit=self.audit)
        self._registrations: list[_Registration] = []
        self._scheduler_tasks: dict[Scope, set[asyncio.Task[None]]] = {}
        self._plugin_scopes: dict[str, Scope] = {}
        self._sequence = 0
        self._subscription: Subscription | None = None
        self._closed = False

    @property
    def tool_handlers(self) -> Mapping[str, object]:
        handlers: dict[str, object] = {}
        for registration in self._registrations:
            if registration.kind != "tool":
                continue
            tool_id, handler = cast(tuple[str, object], registration.value)
            handlers[tool_id] = handler
        return handlers

    @property
    def active_plugin_ids(self) -> tuple[str, ...]:
        """Return activated plugin IDs without exposing the internal scope map."""

        return tuple(self._plugin_scopes)

    async def activate(self, plugin_id: str, factory: PluginFactory, *, declared_tools: tuple[str, ...] = ()) -> Scope:
        if plugin_id in self._plugin_scopes:
            raise ValueError(f"Cordis plugin {plugin_id!r} is already activated")
        scope = self.scope.child(plugin_id=plugin_id)
        started = monotonic()
        try:
            result = factory(scope)
            if inspect.isawaitable(result):
                await result
            registered_tools = tuple(
                cast(tuple[str, object], item.value)[0]
                for item in self._registrations
                if _scope_belongs_to(item.scope, scope) and item.kind == "tool"
            )
            if set(registered_tools) != set(declared_tools) or len(registered_tools) != len(declared_tools):
                raise ValueError(f"Cordis plugin {plugin_id!r} must register exactly one handler per declared Tool")
        except BaseException as error:
            await scope.aclose()
            self.audit.record(
                plugin_id=plugin_id,
                scope_id=scope.id,
                event_id=None,
                operation="plugin.activate",
                outcome="error",
                started_at=started,
                error=error,
            )
            raise
        self._plugin_scopes[plugin_id] = scope
        self.audit.record(
            plugin_id=plugin_id,
            scope_id=scope.id,
            event_id=None,
            operation="plugin.activate",
            outcome="ok",
            started_at=started,
        )
        return scope

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("Cordis manager is closed")
        if self._subscription is None:
            self._subscription = self.events.subscribe(self._handle_event, name="cordis.manager")

    def register(self, scope: Scope, kind: str, value: object) -> Disposer:
        if self._closed:
            raise RuntimeError("Cordis manager is closed")
        registration = _Registration(scope, kind, value, self._sequence)
        self._sequence += 1
        self._registrations.append(registration)
        if kind == "scheduler":
            tasks = self._scheduler_tasks.get(scope)
            if tasks is None:
                tasks = set()
                self._scheduler_tasks[scope] = tasks
                scope.own(_task_set_disposer(tasks))

        def dispose() -> None:
            with contextlib.suppress(ValueError):
                self._registrations.remove(registration)
            if kind == "scheduler" and not any(
                item.scope is scope and item.kind == "scheduler" for item in self._registrations
            ):
                self._scheduler_tasks.pop(scope, None)

        return dispose

    async def _handle_event(self, envelope: EventEnvelope) -> HandlerResult:
        result = await self.dispatch(envelope)
        return HandlerResult(actions=result.actions)

    async def dispatch(self, envelope: EventEnvelope) -> CordisDispatchResult:
        event = CordisEvent(envelope)
        event_scope = self.scope.child(plugin_id="event")
        session = CordisSession(event, event_scope, self.actions)
        failures: list[str] = []
        try:
            registrations = tuple(self._registrations)
            await self._run_ordered(session, registrations, failures)
            await self._run_parallel(session, registrations, failures)
            await self._run_waterfall(session, registrations, failures)
            await self._run_routes(session, registrations, failures)
            self._schedule_custom(event, registrations)
            return CordisDispatchResult(tuple(session._emitted), tuple(failures), tuple(session._action_results))
        finally:
            await event_scope.aclose()

    async def _run_ordered(
        self, session: CordisSession, registrations: tuple[_Registration, ...], failures: list[str]
    ) -> None:
        ordered = sorted(
            (item for item in registrations if item.kind == "ordered"),
            key=lambda item: (cast(tuple[int, object], item.value)[0], item.sequence),
        )
        for item in ordered:
            handler = cast(OrderedHandler, cast(tuple[int, object], item.value)[1])

            def invoke(handler: OrderedHandler = handler) -> Awaitable[None] | None:
                return handler(session)

            if not await self._invoke(item, "ordered", session.event.envelope.id, invoke, failures):
                return

    async def _run_parallel(
        self, session: CordisSession, registrations: tuple[_Registration, ...], failures: list[str]
    ) -> None:
        branches = [item for item in registrations if item.kind == "parallel"]
        if not branches:
            return

        async def run_branch(item: _Registration) -> tuple[CordisSession, list[str]]:
            branch_scope = session.scope.child(plugin_id=item.scope.plugin_id)
            branch = CordisSession(session.event, branch_scope, self.actions)
            branch_failures: list[str] = []
            await self._invoke(
                item,
                "parallel",
                session.event.envelope.id,
                _session_callback(branch, cast(ParallelHandler, item.value)),
                branch_failures,
            )
            return branch, branch_failures

        results = await asyncio.gather(*(run_branch(item) for item in branches))
        for branch, branch_failures in results:
            session._emitted.extend(branch._emitted)
            session._action_results.extend(branch._action_results)
            failures.extend(branch_failures)

    async def _run_waterfall(
        self, session: CordisSession, registrations: tuple[_Registration, ...], failures: list[str]
    ) -> None:
        stages = [item for item in registrations if item.kind == "waterfall"]

        async def call(index: int) -> None:
            if index >= len(stages):
                return
            item = stages[index]
            called = False

            async def next_stage() -> None:
                nonlocal called
                if called:
                    raise RuntimeError("Cordis waterfall next() may be called at most once")
                called = True
                await call(index + 1)

            await self._invoke(
                item,
                "waterfall",
                session.event.envelope.id,
                lambda: cast(WaterfallHandler, item.value)(session, next_stage),
                failures,
            )

        await call(0)

    async def _run_routes(
        self, session: CordisSession, registrations: tuple[_Registration, ...], failures: list[str]
    ) -> None:
        for item in (item for item in registrations if item.kind == "route"):
            name, predicate, handler = cast(tuple[str, RoutePredicate, OrderedHandler], item.value)
            try:
                matched = predicate(session.event)
                if inspect.isawaitable(matched):
                    matched = await matched
            except Exception as error:
                self._record_failure(item, f"route:{name}:predicate", session.event.envelope.id, failures, error)
                continue
            if matched:

                def invoke(handler: OrderedHandler = handler) -> Awaitable[None] | None:
                    return handler(session)

                await self._invoke(
                    item,
                    f"route:{name}",
                    session.event.envelope.id,
                    invoke,
                    failures,
                )

    def _schedule_custom(self, event: CordisEvent, registrations: tuple[_Registration, ...]) -> None:
        work = tuple(item.value for item in registrations if item.kind != "scheduler")
        for item in (item for item in registrations if item.kind == "scheduler"):
            tasks = self._scheduler_tasks.setdefault(item.scope, set())
            task = asyncio.create_task(
                self._run_scheduler(item, event, work), name=f"cordis-scheduler-{item.scope.plugin_id}"
            )
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    async def _run_scheduler(self, item: _Registration, event: CordisEvent, work: tuple[object, ...]) -> None:
        scheduler = cast(Scheduler, item.value)

        def invoke() -> Awaitable[None] | None:
            return scheduler(event, work)

        await self._invoke(item, "scheduler", event.envelope.id, invoke, [])

    async def _invoke(
        self,
        item: _Registration,
        operation: str,
        event_id: str,
        callback: Callable[[], object],
        failures: list[str],
    ) -> bool:
        started = monotonic()
        try:
            result = callback()
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._record_failure(item, operation, event_id, failures, error, started)
            return False
        self.audit.record(
            plugin_id=item.scope.plugin_id,
            scope_id=item.scope.id,
            event_id=event_id,
            operation=operation,
            outcome="ok",
            started_at=started,
        )
        return True

    def _record_failure(
        self,
        item: _Registration,
        operation: str,
        event_id: str,
        failures: list[str],
        error: Exception,
        started: float | None = None,
    ) -> None:
        failures.append(f"{operation}: {type(error).__name__}")
        self.audit.record(
            plugin_id=item.scope.plugin_id,
            scope_id=item.scope.id,
            event_id=event_id,
            operation=operation,
            outcome="error",
            started_at=started,
            error=error,
        )

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._subscription is not None:
            self.events.unsubscribe(self._subscription)
            self._subscription = None
        await self.scope.aclose()


async def _cancel_task(task: asyncio.Task[object]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def _session_callback(session: CordisSession, handler: OrderedHandler) -> Callable[[], Awaitable[None] | None]:
    def invoke() -> Awaitable[None] | None:
        return handler(session)

    return invoke


def _task_set_disposer(tasks: set[asyncio.Task[None]]) -> Disposer:
    async def dispose() -> None:
        await asyncio.gather(*(_cancel_task(task) for task in tuple(tasks)), return_exceptions=True)

    return dispose


def _scope_belongs_to(scope: Scope, parent: Scope) -> bool:
    current: Scope | None = scope
    while current is not None:
        if current is parent:
            return True
        current = current.parent
    return False
