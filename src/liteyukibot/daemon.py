"""One local daemon supervising one independently restartable kernel worker."""

from __future__ import annotations

import asyncio
import os
import signal
from collections import deque
from collections.abc import Mapping, Sequence
from time import monotonic
from typing import Any

from .config import DaemonSettings
from .control import ControlServer
from .instances import InstancePaths


class InstanceDaemon:
    """Supervise a worker without owning the worker's data-directory lock."""

    def __init__(
        self,
        paths: InstancePaths,
        settings: DaemonSettings,
        worker_command: Sequence[str],
        worker_environment: Mapping[str, str],
    ) -> None:
        self.paths = paths
        self.settings = settings
        self.worker_command = tuple(worker_command)
        self.worker_environment = dict(worker_environment)
        self.worker: asyncio.subprocess.Process | None = None
        self._stop_event = asyncio.Event()
        self._restart_event = asyncio.Event()
        self._failures: deque[float] = deque()
        self._last_exit_code: int | None = None
        self._started_at = monotonic()
        self.control = ControlServer(
            paths.daemon_descriptor,
            status_provider=self.status,
            handlers={"stop": self._request_stop, "restart": self._request_restart},
        )

    def status(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "instance": self.paths.name,
            "state": "stopping" if self._stop_event.is_set() else "running",
            "uptime_seconds": max(0.0, monotonic() - self._started_at),
            "worker": {
                "pid": self.worker.pid if self.worker is not None else None,
                "returncode": self.worker.returncode if self.worker is not None else self._last_exit_code,
            },
            "failures_in_window": len(self._failures),
        }

    async def run(self) -> int:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        await self.control.start()
        try:
            await self._start_worker()
            self._install_signal_handlers()
            while not self._stop_event.is_set():
                outcome = await self._wait_for_worker_change()
                if outcome == "stop":
                    break
                if outcome == "restart":
                    await self._terminate_worker()
                    self._failures.clear()
                    self._restart_event.clear()
                    await self._start_worker()
                    continue
                if self.worker is None:
                    break
                self._last_exit_code = self.worker.returncode
                if self._last_exit_code == 0 or not self.settings.auto_restart or not self._can_restart():
                    return self._last_exit_code or 0
                await asyncio.sleep(self._restart_delay())
                await self._start_worker()
            return 0
        finally:
            await self._terminate_worker()
            await self.control.stop()

    async def _start_worker(self) -> None:
        environment = {**os.environ, **self.worker_environment}
        environment["LITEYUKI_DAEMON_DESCRIPTOR"] = str(self.paths.daemon_descriptor)
        environment["LITEYUKI_DAEMON_WORKER"] = "1"
        self.worker = await asyncio.create_subprocess_exec(*self.worker_command, env=environment)

    async def _wait_for_worker_change(self) -> str:
        assert self.worker is not None
        worker_exit = asyncio.create_task(self.worker.wait(), name="daemon-worker-exit")
        stop_wait = asyncio.create_task(self._stop_event.wait(), name="daemon-stop")
        restart_wait = asyncio.create_task(self._restart_event.wait(), name="daemon-restart")
        done, pending = await asyncio.wait(
            {worker_exit, stop_wait, restart_wait},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if stop_wait in done:
            return "stop"
        if restart_wait in done:
            return "restart"
        return "exit"

    async def _terminate_worker(self) -> None:
        worker = self.worker
        self.worker = None
        if worker is None or worker.returncode is not None:
            return
        worker.terminate()
        try:
            async with asyncio.timeout(10):
                await worker.wait()
        except TimeoutError:
            worker.kill()
            await worker.wait()

    def _can_restart(self) -> bool:
        now = monotonic()
        while self._failures and now - self._failures[0] > self.settings.restart_window_seconds:
            self._failures.popleft()
        self._failures.append(now)
        return len(self._failures) <= self.settings.restart_limit

    def _restart_delay(self) -> float:
        exponent = max(0, len(self._failures) - 1)
        delay = min(
            self.settings.restart_backoff_max_seconds,
            self.settings.restart_backoff_initial_seconds * (2**exponent),
        )
        return float(delay)

    async def _request_stop(self, _request: Mapping[str, Any]) -> dict[str, object]:
        self._stop_event.set()
        return {"accepted": True}

    async def _request_restart(self, _request: Mapping[str, Any]) -> dict[str, object]:
        self._restart_event.set()
        return {"accepted": True}

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, self._stop_event.set)
            except (NotImplementedError, RuntimeError, ValueError):
                try:
                    signal.signal(signum, lambda _signum, _frame: self._stop_event.set())
                except (OSError, RuntimeError, ValueError):
                    continue


__all__ = ["InstanceDaemon"]
