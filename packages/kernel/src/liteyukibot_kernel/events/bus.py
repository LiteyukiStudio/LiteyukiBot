from __future__ import annotations

import asyncio
import contextlib
import inspect
import math
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from yukilog import Logger, get_logger

from .models import ActionEnvelope, ActionResult, DispatchResult, EventEnvelope, HandlerFailure, HandlerResult

type EventHandler = Callable[[EventEnvelope], Awaitable[HandlerResult | None]]
type ActionExecutor = Callable[[EventEnvelope, ActionEnvelope], Awaitable[ActionResult]]
type ActionGuard = Callable[[EventEnvelope, ActionEnvelope], Awaitable[ActionResult | None]]

_CANCELLATION_GRACE_SECONDS = 0.05
_DEFAULT_MAX_EVENT_BYTES = 1024 * 1024


class _OperationTimeout(TimeoutError):
    """Raised when a tracked handler or action task exceeds its deadline."""

    def __init__(self, task: asyncio.Task[Any]) -> None:
        super().__init__()
        self.task = task


def _is_async_callable(value: object) -> bool:
    """Return whether a callback is an async function or async callable object."""

    if inspect.iscoroutinefunction(value):
        return True
    return callable(value) and inspect.iscoroutinefunction(cast(Any, value).__call__)

@dataclass(frozen=True, slots=True)
class Subscription:
    """Represent the subscription contract."""
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class _RegisteredHandler:
    """Represent the registered handler contract."""
    order: int
    sequence: int
    subscription: Subscription
    callback: EventHandler


@dataclass(slots=True)
class _QueuedEvent:
    """Represent the validated queued event contract."""
    event: EventEnvelope
    future: asyncio.Future[DispatchResult]
    completed: bool = False


class EventBus:
    """Bounded event dispatcher with FIFO ordering per conversation key."""

    def __init__(
        self,
        *,
        queue_capacity: int = 1024,
        enqueue_timeout: float = 1.0,
        handler_timeout: float = 30.0,
        action_timeout: float = 30.0,
        close_timeout: float = 10.0,
        max_concurrent_events: int = 100,
        max_event_bytes: int = _DEFAULT_MAX_EVENT_BYTES,
        action_executor: ActionExecutor | None = None,
        action_guard: ActionGuard | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialize the event bus.

        Args:
            queue_capacity: Maximum number of events admitted but not yet completed.
            enqueue_timeout: Maximum time to wait for event capacity, in seconds.
            handler_timeout: Maximum time allowed for one handler invocation, in seconds.
            action_timeout: Maximum time allowed for one action guard or executor, in seconds.
            close_timeout: Maximum time to wait for admitted events during shutdown, in seconds.
            max_concurrent_events: Maximum number of events dispatched concurrently.
            max_event_bytes: Maximum UTF-8 JSON size of one admitted event.
            action_executor: Executor that routes actions to the owning runtime.
            action_guard: Optional policy hook that can reject an action before execution.
            logger: Structured logger used for diagnostics.

        Returns:
            None.
        """
        if queue_capacity < 1:
            raise ValueError("queue_capacity must be at least 1")
        if not math.isfinite(enqueue_timeout) or enqueue_timeout < 0:
            raise ValueError("enqueue_timeout must be finite and non-negative")
        if not math.isfinite(handler_timeout) or handler_timeout <= 0:
            raise ValueError("handler_timeout must be finite and positive")
        if not math.isfinite(action_timeout) or action_timeout <= 0:
            raise ValueError("action_timeout must be finite and positive")
        if not math.isfinite(close_timeout) or close_timeout <= 0:
            raise ValueError("close_timeout must be finite and positive")
        if max_concurrent_events < 1:
            raise ValueError("max_concurrent_events must be at least 1")
        if max_event_bytes < 1:
            raise ValueError("max_event_bytes must be at least 1")
        if action_executor is not None and not _is_async_callable(action_executor):
            raise TypeError("action_executor must be an async callable")
        if action_guard is not None and not _is_async_callable(action_guard):
            raise TypeError("action_guard must be an async callable")

        self._queue_capacity = queue_capacity
        self._enqueue_timeout = enqueue_timeout
        self._handler_timeout = handler_timeout
        self._action_timeout = action_timeout
        self._close_timeout = close_timeout
        self._max_event_bytes = max_event_bytes
        self._action_executor = action_executor
        self._action_guard = action_guard
        self._logger = logger or get_logger(component="events")
        self._capacity = asyncio.BoundedSemaphore(queue_capacity)
        self._concurrency = asyncio.Semaphore(max_concurrent_events)
        self._ingress: asyncio.Queue[_QueuedEvent] = asyncio.Queue()
        self._key_queues: dict[tuple[str, str, str], deque[_QueuedEvent]] = {}
        self._key_workers: dict[tuple[str, str, str], asyncio.Task[None]] = {}
        self._handlers: list[_RegisteredHandler] = []
        self._next_subscription_id = 0
        self._dispatcher: asyncio.Task[None] | None = None
        self._accepting = True
        self._idle = asyncio.Event()
        self._idle.set()
        self._outstanding = 0
        self._in_flight: dict[int, _QueuedEvent] = {}
        self._forced_close = False
        self._operation_tasks: set[asyncio.Task[Any]] = set()

    @property
    def closed(self) -> bool:
        """Return the event bus's closed.

        Returns:
            Whether the requested condition is satisfied.
        """
        return not self._accepting

    @property
    def outstanding(self) -> int:
        """Return the event bus's outstanding.

        Returns:
            The `int` result produced by the operation.
        """
        return self._outstanding

    @property
    def background_tasks(self) -> int:
        """Return tracked dispatcher, worker and callback tasks still alive."""

        dispatcher = int(self._dispatcher is not None and not self._dispatcher.done())
        workers = sum(not task.done() for task in self._key_workers.values())
        operations = sum(not task.done() for task in self._operation_tasks)
        return dispatcher + workers + operations

    def subscribe(self, handler: EventHandler, *, order: int = 0, name: str | None = None) -> Subscription:
        """Register a handler and return its subscription.

        Args:
            handler: Callable that handles the dispatched value.
            order: Relative handler ordering; lower values run first.
            name: Stable name used to identify the value.

        Returns:
            The `Subscription` result produced by the operation.
        """
        if not callable(handler):
            raise TypeError("handler must be callable")
        if not _is_async_callable(handler):
            raise TypeError("EventBus handlers must be async callables")
        sequence = self._next_subscription_id
        self._next_subscription_id += 1
        inferred_name = getattr(handler, "__qualname__", None)
        handler_name = name or (inferred_name if isinstance(inferred_name, str) else repr(handler))
        subscription = Subscription(sequence, handler_name)
        self._handlers.append(_RegisteredHandler(order, sequence, subscription, handler))
        self._handlers.sort(key=lambda registered: (registered.order, registered.sequence))
        return subscription

    def unsubscribe(self, subscription: Subscription) -> bool:
        """Remove a previously registered subscription.

        Args:
            subscription: Previously returned subscription to remove.

        Returns:
            Whether the requested condition is satisfied.
        """
        for index, registered in enumerate(self._handlers):
            if registered.subscription is subscription:
                del self._handlers[index]
                return True
        return False

    async def start(self) -> None:
        """Start the event bus.

        Returns:
            None.
        """
        if not self._accepting:
            raise RuntimeError("event bus is closed")
        if self._dispatcher is None:
            self._dispatcher = asyncio.create_task(self._dispatch_loop(), name="liteyukibot-event-dispatcher")

    async def publish(self, event: EventEnvelope) -> DispatchResult:
        """Publish one event and wait for its dispatch result.

        Args:
            event: Event associated with the operation.

        Returns:
            The `DispatchResult` result produced by the operation.
        """
        if not self._accepting:
            return DispatchResult(event_id=event.id, status="closed")
        if len(event.model_dump_json().encode("utf-8")) > self._max_event_bytes:
            return DispatchResult(event_id=event.id, status="overloaded")
        await self.start()

        try:
            if self._enqueue_timeout == 0:
                if self._capacity.locked():
                    return DispatchResult(event_id=event.id, status="overloaded")
                await self._capacity.acquire()
            else:
                await asyncio.wait_for(self._capacity.acquire(), timeout=self._enqueue_timeout)
        except TimeoutError:
            return DispatchResult(event_id=event.id, status="overloaded")

        if not self._accepting:
            self._capacity.release()
            return DispatchResult(event_id=event.id, status="closed")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[DispatchResult] = loop.create_future()
        self._outstanding += 1
        self._idle.clear()
        self._ingress.put_nowait(_QueuedEvent(event, future))
        return await asyncio.shield(future)

    async def aclose(self) -> None:
        """Close the event bus asynchronously.

        Returns:
            None.
        """
        if not self._accepting:
            return
        self._accepting = False
        try:
            async with asyncio.timeout(self._close_timeout):
                await self._idle.wait()
        except TimeoutError:
            self._logger.warning(
                "event bus shutdown exceeded {} seconds; cancelling admitted events",
                self._close_timeout,
            )
            await self._force_close()
        else:
            await self._cancel_operation_tasks()
        if self._dispatcher is not None:
            self._dispatcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._dispatcher
            self._dispatcher = None

    async def __aenter__(self) -> EventBus:
        """Enter the event bus context.

        Returns:
            The `EventBus` result produced by the operation.
        """
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        """Exit the event bus context.

        Args:
            *_exc_info: Exception context supplied by the asynchronous context manager.

        Returns:
            None.
        """
        await self.aclose()

    async def _dispatch_loop(self) -> None:
        """Dispatch loop.

        Returns:
            None.

        Notes:
            Internal implementation detail for `EventBus._dispatch_loop`. It delegates to `get`,
            `setdefault`, `deque`, `append` while keeping intermediate state local to the owning operation.
        """
        while True:
            queued = await self._ingress.get()
            key = queued.event.ordering_key
            key_queue = self._key_queues.setdefault(key, deque())
            key_queue.append(queued)
            if key not in self._key_workers:
                self._key_workers[key] = asyncio.create_task(
                    self._run_key_queue(key),
                    name=f"liteyukibot-event-key-{key[0]}-{key[1]}-{key[2]}",
                )
            self._ingress.task_done()

    async def _run_key_queue(self, key: tuple[str, str, str]) -> None:
        """Run key queue.

        Args:
            key: Stable FIFO ordering key for the queued work.

        Returns:
            None.

        Notes:
            Internal implementation detail for `EventBus._run_key_queue`. It delegates to `popleft`,
            `_dispatch`, `done`, `set_result` while keeping intermediate state local to the owning
            operation.
        """
        key_queue = self._key_queues[key]
        try:
            while key_queue:
                queued = key_queue.popleft()
                self._in_flight[id(queued)] = queued
                barriers: tuple[asyncio.Task[Any], ...] = ()
                try:
                    async with self._concurrency:
                        result, barriers = await self._dispatch(queued.event)
                    if not queued.future.done():
                        queued.future.set_result(result)
                except BaseException as exc:
                    if not queued.future.done():
                        queued.future.set_exception(exc)
                    if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                        raise
                finally:
                    self._finish_queued(queued)
                await self._wait_for_barriers(barriers)
                await asyncio.sleep(0)
        finally:
            while key_queue:
                self._close_queued(key_queue.popleft())
            if self._outstanding == 0:
                self._idle.set()
            if self._key_queues.get(key) is key_queue:
                del self._key_queues[key]
            if self._key_workers.get(key) is asyncio.current_task():
                del self._key_workers[key]

    async def _dispatch(self, event: EventEnvelope) -> tuple[DispatchResult, tuple[asyncio.Task[Any], ...]]:
        """Dispatch the event bus operation.

        Args:
            event: Event associated with the operation.

        Returns:
            The `DispatchResult` result produced by the operation.

        Notes:
            Internal implementation detail for `EventBus._dispatch`. It delegates to `bind`, `timeout`,
            `callback`, `isawaitable` while keeping intermediate state local to the owning operation.
        """
        if self._forced_close:
            return DispatchResult(event_id=event.id, status="closed"), ()
        event_logger = self._logger.bind(
            event_id=event.id,
            runtime=event.runtime_id,
            bot_id=event.bot_id,
        )
        failures: list[HandlerFailure] = []
        action_results: list[ActionResult] = []
        barriers: list[asyncio.Task[Any]] = []
        pending_action_barriers: list[asyncio.Task[Any]] = []
        handlers_called = 0
        stopped = False

        for registered in tuple(self._handlers):
            handlers_called += 1
            try:
                result = await self._run_operation(
                    registered.callback(event),
                    timeout_seconds=self._handler_timeout,
                    name=f"handler {registered.subscription.name}",
                    barriers=barriers,
                )
            except _OperationTimeout:
                failure = HandlerFailure(
                    handler=registered.subscription.name,
                    kind="timeout",
                    message=f"handler exceeded {self._handler_timeout:g} seconds",
                )
                failures.append(failure)
                event_logger.error("event handler {} timed out", registered.subscription.name)
                continue
            except Exception as exc:
                error_type = type(exc).__name__
                failures.append(
                    HandlerFailure(
                        handler=registered.subscription.name,
                        kind="error",
                        message=f"{error_type}: handler failed",
                    )
                )
                event_logger.error(
                    "event handler {} failed: {}",
                    registered.subscription.name,
                    error_type,
                )
                continue

            if result is None:
                result = HandlerResult()
            elif not isinstance(result, HandlerResult):
                failures.append(
                    HandlerFailure(
                        handler=registered.subscription.name,
                        kind="invalid_result",
                        message=f"expected HandlerResult or None, got {type(result).__name__}",
                    )
                )
                event_logger.error(
                    "event handler {} returned an invalid result",
                    registered.subscription.name,
                )
                continue

            failures.extend(result.failures)
            action_results.extend(result.action_results)
            for action in result.actions:
                pending_action_barriers[:] = [task for task in pending_action_barriers if not task.done()]
                if pending_action_barriers:
                    action_results.append(
                        ActionResult(
                            action_id=action.action_id,
                            success=False,
                            error_code="ACTION_BLOCKED",
                            error_message="a previous action is still running",
                        )
                    )
                    continue
                action_result, new_action_barriers = await self._execute_action(event, action)
                action_results.append(action_result)
                if new_action_barriers:
                    barriers.extend(new_action_barriers)
                    pending_action_barriers.extend(new_action_barriers)
            if result.stop_propagation:
                stopped = True
                break

        return DispatchResult(
            event_id=event.id,
            status="processed",
            handlers_called=handlers_called,
            stopped=stopped,
            action_results=tuple(action_results),
            failures=tuple(failures),
        ), tuple(barriers)

    async def _execute_action(
        self,
        event: EventEnvelope,
        action: ActionEnvelope,
    ) -> tuple[ActionResult, tuple[asyncio.Task[Any], ...]]:
        """Execute one action with a bounded guard and executor lifetime."""

        barriers: list[asyncio.Task[Any]] = []
        try:
            result = cast(
                ActionResult,
                await self._run_operation(
                    self._execute_action_unbounded(event, action),
                    timeout_seconds=self._action_timeout,
                    name=f"action {action.action_id}",
                    barriers=barriers,
                ),
            )
            return result, tuple(barriers)
        except _OperationTimeout:
            self._logger.bind(event_id=event.id, runtime=event.runtime_id, bot_id=event.bot_id).error(
                "action {} exceeded {} seconds", action.action_id, self._action_timeout
            )
            return (
                ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error_code="ACTION_TIMEOUT",
                    error_message=f"action exceeded {self._action_timeout:g} seconds",
                ),
                tuple(barriers),
            )

    async def _execute_action_unbounded(self, event: EventEnvelope, action: ActionEnvelope) -> ActionResult:
        """Execute action.

        Args:
            event: Event associated with the operation.
            action: Action request being processed.

        Returns:
            The `ActionResult` result produced by the operation.

        Notes:
            Internal implementation detail for `EventBus._execute_action`. It delegates to `_action_guard`,
            `isawaitable`, `exception`, `bind` while keeping intermediate state local to the owning
            operation.
        """
        if self._action_guard is not None:
            try:
                guarded: Any = await self._action_guard(event, action)
                if guarded is not None:
                    if not isinstance(guarded, ActionResult):
                        raise TypeError(f"expected ActionResult or None, got {type(guarded).__name__}")
                    if guarded.action_id != action.action_id:
                        raise ValueError("action guard result correlation id does not match the action")
                    return guarded
            except Exception as exc:
                error_type = type(exc).__name__
                self._logger.bind(event_id=event.id, runtime=event.runtime_id, bot_id=event.bot_id).error(
                    "action guard failed for action {}: {}",
                    action.action_id,
                    error_type,
                )
                return ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error_code="ACTION_GUARD_ERROR",
                    error_message=f"{error_type}: action guard failed",
                )
        if self._action_executor is None:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="NO_ACTION_EXECUTOR",
                error_message="the event bus has no action executor",
            )
        try:
            result: Any = await self._action_executor(event, action)
            if not isinstance(result, ActionResult):
                raise TypeError(f"expected ActionResult, got {type(result).__name__}")
            if result.action_id != action.action_id:
                raise ValueError("action result correlation id does not match the action")
            return result
        except Exception as exc:
            error_type = type(exc).__name__
            self._logger.bind(event_id=action.event_id, runtime=action.runtime_id, bot_id=action.bot_id).error(
                "action executor failed for action {}: {}",
                action.action_id,
                error_type,
            )
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="ACTION_EXECUTOR_ERROR",
                error_message=f"{error_type}: action executor failed",
            )

    def _finish_queued(self, queued: _QueuedEvent) -> None:
        """Release admission accounting exactly once for one queued event."""

        if queued.completed:
            return
        queued.completed = True
        self._in_flight.pop(id(queued), None)
        self._outstanding -= 1
        self._capacity.release()
        if self._outstanding == 0:
            self._idle.set()

    async def _force_close(self) -> None:
        """Resolve admitted events and cancel workers after the graceful deadline."""

        self._forced_close = True
        for worker in tuple(self._key_workers.values()):
            worker.cancel()
        await self._cancel_operation_tasks()

        while True:
            try:
                queued = self._ingress.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._ingress.task_done()
            self._close_queued(queued)

        for key_queue in tuple(self._key_queues.values()):
            while key_queue:
                self._close_queued(key_queue.popleft())
            key_queue.clear()
        for queued in tuple(self._in_flight.values()):
            self._close_queued(queued)
        if self._outstanding == 0:
            self._idle.set()

    def _close_queued(self, queued: _QueuedEvent) -> None:
        """Complete one admitted event as closed during forced shutdown."""

        if not queued.future.done():
            queued.future.set_result(DispatchResult(event_id=queued.event.id, status="closed"))
        self._finish_queued(queued)

    async def _run_operation(
        self,
        operation: Awaitable[Any],
        *,
        timeout_seconds: float,
        name: str,
        barriers: list[asyncio.Task[Any]] | None = None,
    ) -> Any:
        """Run one async callback with bounded waiting and tracked cancellation."""

        task = asyncio.ensure_future(operation)
        self._operation_tasks.add(task)
        try:
            done, pending = await asyncio.wait((task,), timeout=timeout_seconds)
            if pending:
                task.cancel()
                done_after_cancel, _ = await asyncio.wait((task,), timeout=_CANCELLATION_GRACE_SECONDS)
                for completed in done_after_cancel:
                    with contextlib.suppress(BaseException):
                        completed.exception()
                if not task.done():
                    self._logger.error("{} did not stop after cancellation", name)
                    if barriers is not None:
                        barriers.append(task)
                raise _OperationTimeout(task)
            return task.result()
        except asyncio.CancelledError:
            if not task.done():
                task.cancel()
                done_after_cancel, _ = await asyncio.wait((task,), timeout=_CANCELLATION_GRACE_SECONDS)
                for completed in done_after_cancel:
                    with contextlib.suppress(BaseException):
                        completed.exception()
                if not task.done() and barriers is not None:
                    barriers.append(task)
            raise
        finally:
            if task.done():
                self._operation_tasks.discard(task)
            else:
                task.add_done_callback(self._forget_operation)

    def _forget_operation(self, task: asyncio.Task[Any]) -> None:
        """Drop a tracked operation after an uncooperative callback eventually ends."""

        self._operation_tasks.discard(task)
        if not task.cancelled():
            with contextlib.suppress(BaseException):
                task.exception()

    async def _wait_for_barriers(self, barriers: tuple[asyncio.Task[Any], ...]) -> None:
        """Wait for timed-out work before processing the next event for the same key."""

        current = asyncio.current_task()
        for task in barriers:
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                if current is not None and current.cancelling():
                    raise
            except BaseException:
                with contextlib.suppress(BaseException):
                    task.exception()

    async def _cancel_operation_tasks(self) -> None:
        """Cancel tracked callback tasks without making shutdown unbounded."""

        tasks = tuple(self._operation_tasks)
        for task in tasks:
            task.cancel()
        if not tasks:
            return
        done, pending = await asyncio.wait(tasks, timeout=_CANCELLATION_GRACE_SECONDS)
        for task in done:
            self._forget_operation(task)
        if pending:
            self._logger.error("{} callback tasks remained after shutdown cancellation", len(pending))
