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
        self._closed = False
        self._accepted = 0
        self._completed = 0
        self._failed = 0
        self._dropped = 0

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def stats(self) -> IngressPublisherStats:
        return IngressPublisherStats(
            accepted=self._accepted,
            completed=self._completed,
            failed=self._failed,
            dropped=self._dropped,
            pending=self._queue.qsize(),
        )

    async def start(self) -> None:
        """Start the single FIFO delivery worker."""

        if self._closed:
            raise RuntimeError("ingress publisher is closed")
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=self._task_name)

    def submit(self, item: T) -> bool:
        """Queue one item immediately, returning false when it cannot be queued."""

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
        """Stop delivery and account for items left in the bounded queue."""

        if self._closed:
            return
        self._closed = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._dropped += 1

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                await asyncio.wait_for(self._handler(item), timeout=self._timeout_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._failed += 1
                self._report_error(error)
            else:
                self._completed += 1

    def _report_error(self, error: Exception) -> None:
        if self._on_error is None:
            return
        try:
            self._on_error(error)
        except Exception:
            return


__all__ = ["BoundedIngressPublisher", "IngressPublisherStats"]
