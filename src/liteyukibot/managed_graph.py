"""Deterministic Broker, bridge, and Kernel process graph ownership."""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


class ManagedGraphError(RuntimeError):
    """Raised when a managed process graph cannot reach the requested state."""


class ProcessLike(Protocol):
    @property
    def pid(self) -> int: ...

    @property
    def returncode(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    async def wait(self) -> int: ...


@dataclass(frozen=True, slots=True)
class ProcessSpec:
    name: str
    command: tuple[str, ...]
    environment: Mapping[str, str]


ProcessLauncher = Callable[[ProcessSpec], Awaitable[ProcessLike]]


async def launch_process(spec: ProcessSpec) -> ProcessLike:
    return await asyncio.create_subprocess_exec(*spec.command, env=dict(spec.environment))


async def terminate_process_tree(pid: int) -> None:
    """Best-effort termination for a process recorded before daemon restart."""

    if pid <= 0:
        return
    if os.name == "nt":
        try:
            process = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            return
        await process.wait()
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


class ManagedProcessGraph:
    """Own all instance processes and expose one explicit start/stop ordering."""

    def __init__(
        self,
        specs: Sequence[ProcessSpec],
        *,
        launcher: ProcessLauncher = launch_process,
        startup_timeout_seconds: float = 30.0,
        stop_timeout_seconds: float = 10.0,
    ) -> None:
        names = tuple(spec.name for spec in specs)
        if len(names) != len(set(names)) or "kernel" not in names:
            raise ValueError("managed graph must contain one uniquely named kernel")
        if names[0] != "broker" and "broker" in names:
            raise ValueError("managed graph must start with broker")
        self.specs = tuple(specs)
        self.launcher = launcher
        self.startup_timeout_seconds = startup_timeout_seconds
        self.stop_timeout_seconds = stop_timeout_seconds
        self.processes: dict[str, ProcessLike] = {}

    @property
    def start_order(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.specs)

    @property
    def stop_order(self) -> tuple[str, ...]:
        return tuple(reversed(self.start_order))

    @property
    def managed(self) -> bool:
        return self.start_order[0] == "broker" and "kernel" in self.start_order

    async def start(self) -> None:
        if self.processes:
            if all(process.returncode is not None for process in self.processes.values()):
                self.processes.clear()
            else:
                raise ManagedGraphError("managed process graph is already running")
        try:
            for spec in self.specs:
                process = await self.launcher(spec)
                self.processes[spec.name] = process
                await self._wait_ready(spec.name, process)
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        for name in self.stop_order:
            process = self.processes.pop(name, None)
            if process is None or process.returncode is not None:
                continue
            process.terminate()
            try:
                async with asyncio.timeout(self.stop_timeout_seconds):
                    await process.wait()
            except TimeoutError:
                process.kill()
                await process.wait()

    async def _wait_ready(self, name: str, process: ProcessLike) -> None:
        try:
            await asyncio.wait_for(asyncio.sleep(0.02), timeout=self.startup_timeout_seconds)
        except TimeoutError as error:
            raise ManagedGraphError(f"managed process {name!r} did not become ready") from error
        if process.returncode is not None and name != "kernel":
            raise ManagedGraphError(f"managed process {name!r} exited before readiness: {process.returncode}")

    def status(self) -> dict[str, object]:
        return {
            "managed": self.managed,
            "start_order": list(self.start_order),
            "stop_order": list(self.stop_order),
            "processes": {
                name: {"pid": process.pid, "returncode": process.returncode}
                for name, process in self.processes.items()
            },
        }


__all__ = [
    "ManagedGraphError",
    "ManagedProcessGraph",
    "ProcessLike",
    "ProcessSpec",
    "launch_process",
    "terminate_process_tree",
]
