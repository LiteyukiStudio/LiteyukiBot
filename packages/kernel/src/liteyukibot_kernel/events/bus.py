from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from yukilog import Logger, get_logger

from .models import ActionEnvelope, ActionResult, DispatchResult, EventEnvelope, HandlerFailure, HandlerResult

type EventHandler = Callable[[EventEnvelope], Awaitable[HandlerResult | None] | HandlerResult | None]
type ActionExecutor = Callable[[EventEnvelope, ActionEnvelope], Awaitable[ActionResult] | ActionResult]
type ActionGuard = Callable[[EventEnvelope, ActionEnvelope], Awaitable[ActionResult | None] | ActionResult | None]

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


class EventBus:
    """Bounded event dispatcher with FIFO ordering per conversation key."""

    def __init__(
        self,
        *,
        queue_capacity: int = 1024,
        enqueue_timeout: float = 1.0,
        handler_timeout: float = 30.0,
        max_concurrent_events: int = 100,
        action_executor: ActionExecutor | None = None,
        action_guard: ActionGuard | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialize the event bus.

        Args:
            queue_capacity: Maximum number of events admitted but not yet completed.
            enqueue_timeout: Maximum time to wait for event capacity, in seconds.
            handler_timeout: Maximum time allowed for one handler invocation, in seconds.
            max_concurrent_events: Maximum number of events dispatched concurrently.
            action_executor: Executor that routes actions to the owning runtime.
            action_guard: Optional policy hook that can reject an action before execution.
            logger: Structured logger used for diagnostics.

        Returns:
            None.
        """
        if queue_capacity < 1:
            raise ValueError("queue_capacity must be at least 1")
        if enqueue_timeout < 0:
            raise ValueError("enqueue_timeout must not be negative")
        if handler_timeout <= 0:
            raise ValueError("handler_timeout must be positive")
        if max_concurrent_events < 1:
            raise ValueError("max_concurrent_events must be at least 1")

        self._queue_capacity = queue_capacity
        self._enqueue_timeout = enqueue_timeout
        self._handler_timeout = handler_timeout
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
            if registered.subscription.id == subscription.id:
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
        await self._idle.wait()
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
                try:
                    async with self._concurrency:
                        result = await self._dispatch(queued.event)
                    if not queued.future.done():
                        queued.future.set_result(result)
                except BaseException as exc:
                    if not queued.future.done():
                        queued.future.set_exception(exc)
                    if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                        raise
                finally:
                    self._outstanding -= 1
                    self._capacity.release()
                    if self._outstanding == 0:
                        self._idle.set()
                await asyncio.sleep(0)
        finally:
            del self._key_queues[key]
            del self._key_workers[key]

    async def _dispatch(self, event: EventEnvelope) -> DispatchResult:
        """Dispatch the event bus operation.

        Args:
            event: Event associated with the operation.

        Returns:
            The `DispatchResult` result produced by the operation.

        Notes:
            Internal implementation detail for `EventBus._dispatch`. It delegates to `bind`, `timeout`,
            `callback`, `isawaitable` while keeping intermediate state local to the owning operation.
        """
        event_logger = self._logger.bind(
            event_id=event.id,
            runtime=event.runtime_id,
            bot_id=event.bot_id,
        )
        failures: list[HandlerFailure] = []
        action_results: list[ActionResult] = []
        handlers_called = 0
        stopped = False

        for registered in tuple(self._handlers):
            handlers_called += 1
            try:
                async with asyncio.timeout(self._handler_timeout):
                    result = registered.callback(event)
                    if inspect.isawaitable(result):
                        result = await result
            except TimeoutError:
                failure = HandlerFailure(
                    handler=registered.subscription.name,
                    kind="timeout",
                    message=f"handler exceeded {self._handler_timeout:g} seconds",
                )
                failures.append(failure)
                event_logger.error("event handler {} timed out", registered.subscription.name)
                continue
            except Exception as exc:
                failures.append(
                    HandlerFailure(
                        handler=registered.subscription.name,
                        kind="error",
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )
                event_logger.exception("event handler {} failed", registered.subscription.name)
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

            for action in result.actions:
                action_results.append(await self._execute_action(event, action))
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
        )

    async def _execute_action(self, event: EventEnvelope, action: ActionEnvelope) -> ActionResult:
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
                guarded: Any = self._action_guard(event, action)
                if inspect.isawaitable(guarded):
                    guarded = await guarded
                if guarded is not None:
                    if not isinstance(guarded, ActionResult):
                        raise TypeError(f"expected ActionResult or None, got {type(guarded).__name__}")
                    if guarded.action_id != action.action_id:
                        raise ValueError("action guard result correlation id does not match the action")
                    return guarded
            except Exception as exc:
                self._logger.bind(event_id=event.id, runtime=event.runtime_id, bot_id=event.bot_id).exception(
                    "action guard failed for action {}", action.action_id
                )
                return ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error_code="ACTION_GUARD_ERROR",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
        if self._action_executor is None:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="NO_ACTION_EXECUTOR",
                error_message="the event bus has no action executor",
            )
        try:
            result: Any = self._action_executor(event, action)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, ActionResult):
                raise TypeError(f"expected ActionResult, got {type(result).__name__}")
            if result.action_id != action.action_id:
                raise ValueError("action result correlation id does not match the action")
            return result
        except Exception as exc:
            self._logger.bind(event_id=action.event_id, runtime=action.runtime_id, bot_id=action.bot_id).exception(
                "action executor failed for action {}", action.action_id
            )
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="ACTION_EXECUTOR_ERROR",
                error_message=f"{type(exc).__name__}: {exc}",
            )
