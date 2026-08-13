from __future__ import annotations

import asyncio

import pytest

from liteyukibot.tasks import ManagedTasks


@pytest.mark.asyncio
async def test_managed_task_failure_is_reported() -> None:
    failures: list[tuple[str, BaseException]] = []
    tasks = ManagedTasks("plugin", lambda name, error: failures.append((name, error)))

    async def fail() -> None:
        raise RuntimeError("broken worker")

    task = tasks.start(fail(), name="worker")
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)

    assert task.done()
    assert len(failures) == 1
    assert failures[0][0] == "plugin:worker"
    assert isinstance(failures[0][1], RuntimeError)
    assert str(failures[0][1]) == "broken worker"
    await tasks.stop()


@pytest.mark.asyncio
async def test_managed_tasks_cancel_on_stop_and_reject_new_work() -> None:
    started = asyncio.Event()
    tasks = ManagedTasks("plugin")

    async def worker() -> None:
        started.set()
        await asyncio.Event().wait()

    task = tasks.start(worker(), name="worker")
    await started.wait()
    await tasks.stop()

    assert task.cancelled()
    pending = asyncio.sleep(0)
    try:
        with pytest.raises(RuntimeError, match="stopping"):
            tasks.start(pending, name="late")
    finally:
        pending.close()
