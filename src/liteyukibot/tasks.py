"""Tracked background tasks owned by an application or plugin."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

type TaskFailureHandler = Callable[[str, BaseException], None]


class ManagedTasks:
    def __init__(self, owner: str, on_failure: TaskFailureHandler | None = None) -> None:
        self.owner = owner
        self._on_failure = on_failure
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closing = False

    def start(self, awaitable: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
        if self._closing:
            raise RuntimeError(f"task owner {self.owner} is stopping")
        task: asyncio.Task[Any] = asyncio.create_task(awaitable, name=f"{self.owner}:{name}")
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None and self._on_failure is not None:
            self._on_failure(task.get_name(), error)

    async def stop(self, timeout_seconds: float = 10.0) -> None:
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
