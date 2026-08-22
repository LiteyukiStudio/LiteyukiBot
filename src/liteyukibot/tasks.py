"""Tracked background tasks owned by an application or plugin."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

type TaskFailureHandler = Callable[[str, BaseException], None]


class ManagedTasks:
    """Represent the managed tasks contract."""
    def __init__(self, owner: str, on_failure: TaskFailureHandler | None = None) -> None:
        """Initialize the managed tasks.

        Args:
            owner: Stable owner identity for the registration.
            on_failure: The on failure value used by the operation.

        Returns:
            None.
        """
        self.owner = owner
        self._on_failure = on_failure
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closing = False

    @property
    def count(self) -> int:
        """Return the managed tasks's count.

        Returns:
            The `int` result produced by the operation.
        """
        return len(self._tasks)

    def start(self, awaitable: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
        """Start the managed tasks.

        Args:
            awaitable: The awaitable value used by the operation.
            name: Stable name used to identify the value.

        Returns:
            The `asyncio.Task[Any]` result produced by the operation.
        """
        if self._closing:
            raise RuntimeError(f"task owner {self.owner} is stopping")
        task: asyncio.Task[Any] = asyncio.create_task(awaitable, name=f"{self.owner}:{name}")
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task[Any]) -> None:
        """Implement the task done operation for the managed tasks.

        Args:
            task: The task value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `ManagedTasks._task_done`. It delegates to `discard`,
            `cancelled`, `exception`, `_on_failure` while keeping intermediate state local to the owning
            operation.
        """
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None and self._on_failure is not None:
            self._on_failure(task.get_name(), error)

    async def stop(self, timeout_seconds: float = 10.0) -> None:
        """Stop the managed tasks and release its owned resources.

        Args:
            timeout_seconds: Maximum duration to wait, in seconds.

        Returns:
            None.
        """
        self._closing = True
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if not tasks:
            return
        try:
            async with asyncio.timeout(timeout_seconds):
                await asyncio.gather(*tasks, return_exceptions=True)
        except TimeoutError as error:
            remaining = sum(not task.done() for task in tasks)
            raise TimeoutError(
                f"{remaining} task(s) owned by {self.owner} ignored cancellation"
            ) from error
