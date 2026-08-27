"""Bounded best-effort publishers for runtime-originated broker ingress."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

type IngressHandler[T] = Callable[[T], Awaitable[None]]
type IngressErrorHandler = Callable[[Exception], None]


@dataclass(frozen=True, slots=True)
class IngressPublisherStats:
    """Counters for one bounded publisher lifetime."""

    accepted: int
    completed: int
    failed: int
    dropped: int
    pending: int


class BoundedIngressPublisher[T]:
    """Deliver queued items without coupling the producer to broker health."""

    def __init__(
        self,
        handler: IngressHandler[T],
        *,
        capacity: int = 256,
        timeout_seconds: float = 1.0,
        on_error: IngressErrorHandler | None = None,
        task_name: str = "liteyuki-ingress-publisher",
    ) -> None:
        """Initialize the bounded ingress publisher.

        Args:
            handler: Callable that handles the dispatched value.
            capacity: The capacity value used by the operation.
            timeout_seconds: Maximum duration to wait, in seconds.
            on_error: The on error value used by the operation.
            task_name: The task name value used by the operation.

        Returns:
            None.

        Notes:
            The future remains tracked until its late result is consumed, so
            closing the publisher can signal it without waiting indefinitely.
        """
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._handler = handler
        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=capacity)
        self._timeout_seconds = timeout_seconds
        self._on_error = on_error
        self._task_name = task_name
        self._task: asyncio.Task[None] | None = None
        self._detached_handlers: set[asyncio.Future[None]] = set()
        self._closed = False
        self._accepted = 0
        self._completed = 0
        self._failed = 0
        self._dropped = 0

    @property
    def closed(self) -> bool:
        """Return the bounded ingress publisher's closed.

        Returns:
            Whether the requested condition is satisfied.
        """
        return self._closed

    @property
    def stats(self) -> IngressPublisherStats:
        """Return the bounded ingress publisher's stats.

        Returns:
            The `IngressPublisherStats` result produced by the operation.
        """
        return IngressPublisherStats(
            accepted=self._accepted,
            completed=self._completed,
            failed=self._failed,
            dropped=self._dropped,
            pending=self._queue.qsize(),
        )

    async def start(self) -> None:
        """Start the single FIFO delivery worker.

        Returns:
            None.

        Notes:
            Late handler failures are consumed because the worker has already
            reported the timeout that detached this future.
        """

        if self._closed:
            raise RuntimeError("ingress publisher is closed")
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=self._task_name)

    def submit(self, item: T) -> bool:
        """Queue one item immediately, returning false when it cannot be queued.

        Args:
            item: The item value used by the operation.

        Returns:
            Whether the requested condition is satisfied.
        """

        if self._closed or self._task is None:
            self._dropped += 1
            return False
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            self._dropped += 1
            return False
        self._accepted += 1
        return True

    async def close(self) -> None:
        """Stop delivery and account for items left in the bounded queue.

        Returns:
            None.
        """

        if self._closed:
            return
        self._closed = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        for handler in tuple(self._detached_handlers):
            handler.cancel()
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._dropped += 1

    async def _run(self) -> None:
        """Run the bounded ingress publisher operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `BoundedIngressPublisher._run`. It delegates to `get`,
            `wait`, `_handler`, `_report_error` while keeping intermediate state local to the owning
            operation.
        """
        while True:
            item = await self._queue.get()
            handler = asyncio.ensure_future(self._handler(item))
            try:
                done, _ = await asyncio.wait((handler,), timeout=self._timeout_seconds)
            except asyncio.CancelledError:
                handler.cancel()
                self._detach_handler(handler)
                raise
            if not done:
                handler.cancel()
                self._detach_handler(handler)
                self._failed += 1
                self._report_error(TimeoutError())
                continue
            try:
                handler.result()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._failed += 1
                self._report_error(error)
            else:
                self._completed += 1

    def _detach_handler(self, handler: asyncio.Future[None]) -> None:
        """Track a timed-out handler without waiting for cancellation completion.

        Args:
            handler: Handler future that may ignore cancellation.

        Returns:
            None.

        Notes:
            The future remains tracked until its late result is consumed, so
            closing the publisher can signal it without waiting indefinitely.
        """
        self._detached_handlers.add(handler)
        handler.add_done_callback(self._finish_detached_handler)

    def _finish_detached_handler(self, handler: asyncio.Future[None]) -> None:
        """Forget a detached handler and consume any late result or failure.

        Args:
            handler: Completed handler future.

        Returns:
            None.

        Notes:
            Late handler failures are consumed because the worker has already
            reported the timeout that detached this future.
        """
        self._detached_handlers.discard(handler)
        try:
            handler.result()
        except BaseException:
            return

    def _report_error(self, error: Exception) -> None:
        """Implement the report error operation for the bounded ingress publisher.

        Args:
            error: The error value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `BoundedIngressPublisher._report_error`. It delegates to
            `_on_error` while keeping intermediate state local to the owning operation.
        """
        if self._on_error is None:
            return
        try:
            self._on_error(error)
        except Exception:
            return


__all__ = ["BoundedIngressPublisher", "IngressPublisherStats"]
