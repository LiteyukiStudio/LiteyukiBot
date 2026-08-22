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
from liteyukibot.runtime_api import RuntimeContextFactory, RuntimeRequirement, RuntimeResolver

from .audit import CordisAuditService
from .scope import Disposer, RegistrationSink, Scope

type OrderedHandler = Callable[[CordisSession], Awaitable[None] | None]
type ParallelHandler = OrderedHandler
type WaterfallHandler = Callable[[CordisSession, Callable[[], Awaitable[None]]], Awaitable[None] | None]
type RoutePredicate = Callable[[CordisEvent], bool | Awaitable[bool]]
type Scheduler = Callable[[CordisEvent, tuple[object, ...]], Awaitable[None] | None]
type PluginFactory = Callable[[Scope], Awaitable[None] | None]


class ActionServiceLike(Protocol):
    """Define the structural interface required from a action service like."""
    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        """Execute one request through the action service like.

        Args:
            action: Action request being processed.
            event: Event associated with the operation.

        Returns:
            The `ActionResult` result produced by the operation.
        """
        ...


@dataclass(frozen=True, slots=True)
class CordisEvent:
    """Represent the validated cordis event contract."""
    envelope: EventEnvelope

    @property
    def raw(self) -> EventEnvelope:
        """Return the cordis event's raw.

        Returns:
            The `EventEnvelope` result produced by the operation.
        """
        return self.envelope


@dataclass(slots=True)
class CordisSession:
    """Represent the cordis session contract."""
    event: CordisEvent
    scope: Scope
    actions: ActionServiceLike
    _emitted: list[ActionEnvelope] = field(default_factory=list)
    _action_results: list[ActionResult] = field(default_factory=list)

    def emit(self, action: ActionEnvelope) -> None:
        """Implement the emit operation for the cordis session.

        Args:
            action: Action request being processed.

        Returns:
            None.
        """
        self._emitted.append(self._bind(action))

    async def execute(self, action: ActionEnvelope) -> ActionResult:
        """Execute one request through the cordis session.

        Args:
            action: Action request being processed.

        Returns:
            The `ActionResult` result produced by the operation.
        """
        action = self._bind(action)
        result = await self.actions.execute(action, event=self.event.envelope)
        self._action_results.append(result)
        return result

    def _bind(self, action: ActionEnvelope) -> ActionEnvelope:
        """Bind the cordis session operation.

        Args:
            action: Action request being processed.

        Returns:
            The `ActionEnvelope` result produced by the operation.

        Notes:
            Internal implementation detail for `CordisSession._bind`. It delegates to `model_copy` while
            keeping intermediate state local to the owning operation.
        """
        if action.event_id not in (None, self.event.envelope.id):
            raise ValueError("Cordis action event_id must match the wrapped event")
        if action.event_id is None:
            return action.model_copy(update={"event_id": self.event.envelope.id})
        return action


@dataclass(frozen=True, slots=True)
class CordisDispatchResult:
    """Represent the validated cordis dispatch result contract."""
    actions: tuple[ActionEnvelope, ...]
    failures: tuple[str, ...]
    action_results: tuple[ActionResult, ...] = ()


@dataclass(frozen=True, slots=True)
class _Registration:
    """Represent the registration contract."""
    scope: Scope
    kind: str
    value: object
    sequence: int


class CordisManager(RegistrationSink):
    """One EventBus subscriber that composes Cordis plugin registrations."""

    def __init__(
        self,
        events: EventBus,
        actions: ActionServiceLike,
        *,
        audit: CordisAuditService | None = None,
        runtime_context_factory: Callable[[str], RuntimeContextFactory] | None = None,
        runtime_resolver: RuntimeResolver | None = None,
    ) -> None:
        """Initialize the cordis manager.

        Args:
            events: The events value used by the operation.
            actions: The actions value used by the operation.
            audit: The audit value used by the operation.
            runtime_context_factory: The runtime context factory value used by the operation.
            runtime_resolver: The runtime resolver value used by the operation.

        Returns:
            None.
        """
        self.events = events
        self.actions = actions
        self.audit = audit or CordisAuditService()
        self.scope = Scope(
            plugin_id="liteyukibot.cordis",
            sink=self,
            audit=self.audit,
            runtime_context_factory=runtime_context_factory,
            runtime_resolver=runtime_resolver,
        )
        self._registrations: list[_Registration] = []
        self._scheduler_tasks: dict[Scope, set[asyncio.Task[None]]] = {}
        self._plugin_scopes: dict[str, Scope] = {}
        self._sequence = 0
        self._subscription: Subscription | None = None
        self._closed = False

    @property
    def tool_handlers(self) -> Mapping[str, object]:
        """Return the cordis manager's tool handlers.

        Returns:
            The `Mapping[str, object]` result produced by the operation.
        """
        handlers: dict[str, object] = {}
        for registration in self._registrations:
            if registration.kind != "tool":
                continue
            tool_id, handler = cast(tuple[str, object], registration.value)
            handlers[tool_id] = handler
        return handlers

    @property
    def active_plugin_ids(self) -> tuple[str, ...]:
        """Return activated plugin IDs without exposing the internal scope map.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """

        return tuple(self._plugin_scopes)

    async def activate(
        self,
        plugin_id: str,
        factory: PluginFactory,
        *,
        declared_tools: tuple[str, ...] = (),
        runtime_requirements: tuple[RuntimeRequirement, ...] = (),
    ) -> Scope:
        """Activate the cordis manager operation.

        Args:
            plugin_id: Stable identifier for the plugin.
            factory: The factory value used by the operation.
            declared_tools: The declared tools value used by the operation.
            runtime_requirements: The runtime requirements value used by the operation.

        Returns:
            The `Scope` result produced by the operation.
        """
        if plugin_id in self._plugin_scopes:
            raise ValueError(f"Cordis plugin {plugin_id!r} is already activated")
        scope = self.scope.child(plugin_id=plugin_id, runtime_requirements=runtime_requirements)
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
        """Start the cordis manager.

        Returns:
            None.
        """
        if self._closed:
            raise RuntimeError("Cordis manager is closed")
        if self._subscription is None:
            self._subscription = self.events.subscribe(self._handle_event, name="cordis.manager")

    def register(self, scope: Scope, kind: str, value: object) -> Disposer:
        """Register the cordis manager operation.

        Args:
            scope: The scope value used by the operation.
            kind: The kind value used by the operation.
            value: Value to validate, transform, or store.

        Returns:
            The `Disposer` result produced by the operation.
        """
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
            """Implement the dispose operation for the register.

            Returns:
                None.

            Notes:
                Internal implementation detail for `CordisManager.register.dispose`. It delegates to `suppress`,
                `remove`, `any`, `pop` while keeping intermediate state local to the owning operation.
            """
            with contextlib.suppress(ValueError):
                self._registrations.remove(registration)
            if kind == "scheduler" and not any(
                item.scope is scope and item.kind == "scheduler" for item in self._registrations
            ):
                self._scheduler_tasks.pop(scope, None)

        return dispose

    async def _handle_event(self, envelope: EventEnvelope) -> HandlerResult:
        """Handle event.

        Args:
            envelope: The envelope value used by the operation.

        Returns:
            The `HandlerResult` result produced by the operation.

        Notes:
            Internal implementation detail for `CordisManager._handle_event`. It delegates to `dispatch`
            while keeping intermediate state local to the owning operation.
        """
        result = await self.dispatch(envelope)
        return HandlerResult(actions=result.actions)

    async def dispatch(self, envelope: EventEnvelope) -> CordisDispatchResult:
        """Dispatch the cordis manager operation.

        Args:
            envelope: The envelope value used by the operation.

        Returns:
            The `CordisDispatchResult` result produced by the operation.
        """
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
        """Run ordered.

        Args:
            session: The session value used by the operation.
            registrations: The registrations value used by the operation.
            failures: The failures value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `CordisManager._run_ordered`. It delegates to `sorted`,
            `cast`, `_invoke` while keeping intermediate state local to the owning operation.
        """
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
        """Run parallel.

        Args:
            session: The session value used by the operation.
            registrations: The registrations value used by the operation.
            failures: The failures value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `CordisManager._run_parallel`. It delegates to `gather`,
            `run_branch`, `extend` while keeping intermediate state local to the owning operation.
        """
        branches = [item for item in registrations if item.kind == "parallel"]
        if not branches:
            return

        async def run_branch(item: _Registration) -> tuple[CordisSession, list[str]]:
            """Run branch.

            Args:
                item: The item value used by the operation.

            Returns:
                The `tuple[CordisSession, list[str]]` result produced by the operation.

            Notes:
                Internal implementation detail for `CordisManager._run_parallel.run_branch`. It delegates to
                `child`, `_invoke`, `_session_callback`, `cast` while keeping intermediate state local to the
                owning operation.
            """
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
        """Run waterfall.

        Args:
            session: The session value used by the operation.
            registrations: The registrations value used by the operation.
            failures: The failures value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `CordisManager._run_waterfall`. It delegates to `call` while
            keeping intermediate state local to the owning operation.
        """
        stages = [item for item in registrations if item.kind == "waterfall"]

        async def call(index: int) -> None:
            """Implement the call operation for the run waterfall.

            Args:
                index: The index value used by the operation.

            Returns:
                None.

            Notes:
                Internal implementation detail for `CordisManager._run_waterfall.call`. It delegates to
                `_invoke`, `cast` while keeping intermediate state local to the owning operation.
            """
            if index >= len(stages):
                return
            item = stages[index]
            called = False

            async def next_stage() -> None:
                """Implement the next stage operation for the call.

                Returns:
                    None.

                Notes:
                    Internal implementation detail for `CordisManager._run_waterfall.call.next_stage`. It delegates
                    to `call` while keeping intermediate state local to the owning operation.
                """
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
        """Run routes.

        Args:
            session: The session value used by the operation.
            registrations: The registrations value used by the operation.
            failures: The failures value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `CordisManager._run_routes`. It delegates to `cast`,
            `predicate`, `isawaitable`, `_record_failure` while keeping intermediate state local to the
            owning operation.
        """
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
        """Implement the schedule custom operation for the cordis manager.

        Args:
            event: Event associated with the operation.
            registrations: The registrations value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `CordisManager._schedule_custom`. It delegates to
            `setdefault`, `create_task`, `_run_scheduler`, `add` while keeping intermediate state local to
            the owning operation.
        """
        work = tuple(item.value for item in registrations if item.kind != "scheduler")
        for item in (item for item in registrations if item.kind == "scheduler"):
            tasks = self._scheduler_tasks.setdefault(item.scope, set())
            task = asyncio.create_task(
                self._run_scheduler(item, event, work), name=f"cordis-scheduler-{item.scope.plugin_id}"
            )
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    async def _run_scheduler(self, item: _Registration, event: CordisEvent, work: tuple[object, ...]) -> None:
        """Run scheduler.

        Args:
            item: The item value used by the operation.
            event: Event associated with the operation.
            work: The work value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `CordisManager._run_scheduler`. It delegates to `cast`,
            `_invoke` while keeping intermediate state local to the owning operation.
        """
        scheduler = cast(Scheduler, item.value)

        def invoke() -> Awaitable[None] | None:
            """Invoke the run scheduler operation.

            Returns:
                The `Awaitable[None] | None` result produced by the operation.

            Notes:
                Internal implementation detail for `CordisManager._run_scheduler.invoke`. It delegates to
                `scheduler` while keeping intermediate state local to the owning operation.
            """
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
        """Invoke the cordis manager operation.

        Args:
            item: The item value used by the operation.
            operation: The operation value used by the operation.
            event_id: Stable event identifier.
            callback: Callback invoked by the operation.
            failures: The failures value used by the operation.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `CordisManager._invoke`. It delegates to `monotonic`,
            `callback`, `isawaitable`, `_record_failure` while keeping intermediate state local to the
            owning operation.
        """
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
        """Record failure.

        Args:
            item: The item value used by the operation.
            operation: The operation value used by the operation.
            event_id: Stable event identifier.
            failures: The failures value used by the operation.
            error: The error value used by the operation.
            started: The started value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `CordisManager._record_failure`. It delegates to `append`,
            `record` while keeping intermediate state local to the owning operation.
        """
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
        """Close the cordis manager asynchronously.

        Returns:
            None.
        """
        if self._closed:
            return
        self._closed = True
        if self._subscription is not None:
            self.events.unsubscribe(self._subscription)
            self._subscription = None
        await self.scope.aclose()


async def _cancel_task(task: asyncio.Task[object]) -> None:
    """Implement the cancel task operation for the component.

    Args:
        task: The task value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_cancel_task`. It delegates to `cancel`, `suppress` while
        keeping intermediate state local to the owning operation.
    """
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def _session_callback(session: CordisSession, handler: OrderedHandler) -> Callable[[], Awaitable[None] | None]:
    """Implement the session callback operation for the component.

    Args:
        session: The session value used by the operation.
        handler: Callable that handles the dispatched value.

    Returns:
        The `Callable[[], Awaitable[None] | None]` result produced by the operation.

    Notes:
        Internal implementation detail for `_session_callback`. It performs the local state transition
        directly and is not a stable extension boundary.
    """
    def invoke() -> Awaitable[None] | None:
        """Invoke the session callback operation.

        Returns:
            The `Awaitable[None] | None` result produced by the operation.

        Notes:
            Internal implementation detail for `_session_callback.invoke`. It delegates to `handler` while
            keeping intermediate state local to the owning operation.
        """
        return handler(session)

    return invoke


def _task_set_disposer(tasks: set[asyncio.Task[None]]) -> Disposer:
    """Implement the task set disposer operation for the component.

    Args:
        tasks: The tasks value used by the operation.

    Returns:
        The `Disposer` result produced by the operation.

    Notes:
        Internal implementation detail for `_task_set_disposer`. It performs the local state transition
        directly and is not a stable extension boundary.
    """
    async def dispose() -> None:
        """Implement the dispose operation for the task set disposer.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_task_set_disposer.dispose`. It delegates to `gather`,
            `_cancel_task` while keeping intermediate state local to the owning operation.
        """
        await asyncio.gather(*(_cancel_task(task) for task in tuple(tasks)), return_exceptions=True)

    return dispose


def _scope_belongs_to(scope: Scope, parent: Scope) -> bool:
    """Implement the scope belongs to operation for the component.

    Args:
        scope: The scope value used by the operation.
        parent: The parent value used by the operation.

    Returns:
        Whether the requested condition is satisfied.

    Notes:
        Internal implementation detail for `_scope_belongs_to`. It performs the local state transition
        directly and is not a stable extension boundary.
    """
    current: Scope | None = scope
    while current is not None:
        if current is parent:
            return True
        current = current.parent
    return False
