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
    """Define the structural interface required from a process like."""
    @property
    def pid(self) -> int:
        """Return the process like's pid.

        Returns:
            The `int` result produced by the operation.
        """
        ...

    @property
    def returncode(self) -> int | None:
        """Return the process like's returncode.

        Returns:
            The `int | None` result produced by the operation.
        """
        ...

    def terminate(self) -> None:
        """Implement the terminate operation for the process like.

        Returns:
            None.
        """
        ...

    def kill(self) -> None:
        """Implement the kill operation for the process like.

        Returns:
            None.
        """
        ...

    async def wait(self) -> int:
        """Wait for the process like operation.

        Returns:
            The `int` result produced by the operation.
        """
        ...


@dataclass(frozen=True, slots=True)
class ProcessSpec:
    """Represent the process spec contract."""
    name: str
    command: tuple[str, ...]
    environment: Mapping[str, str]


ProcessLauncher = Callable[[ProcessSpec], Awaitable[ProcessLike]]


async def launch_process(spec: ProcessSpec) -> ProcessLike:
    """Launch process.

    Args:
        spec: The spec value used by the operation.

    Returns:
        The `ProcessLike` result produced by the operation.
    """
    return await asyncio.create_subprocess_exec(*spec.command, env=dict(spec.environment))


async def terminate_process_tree(pid: int) -> None:
    """Best-effort termination for a process recorded before daemon restart.

    Args:
        pid: The pid value used by the operation.

    Returns:
        None.
    """

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
        """Initialize the managed process graph.

        Args:
            specs: The specs value used by the operation.
            launcher: The launcher value used by the operation.
            startup_timeout_seconds: Configured startup timeout duration, in seconds.
            stop_timeout_seconds: Configured stop timeout duration, in seconds.

        Returns:
            None.
        """
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
        """Return the managed process graph's start order.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        return tuple(spec.name for spec in self.specs)

    @property
    def stop_order(self) -> tuple[str, ...]:
        """Return the managed process graph's stop order.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        return tuple(reversed(self.start_order))

    @property
    def managed(self) -> bool:
        """Return the managed process graph's managed.

        Returns:
            Whether the requested condition is satisfied.
        """
        return self.start_order[0] == "broker" and "kernel" in self.start_order

    async def start(self) -> None:
        """Start the managed process graph.

        Returns:
            None.
        """
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
        """Stop the managed process graph and release its owned resources.

        Returns:
            None.
        """
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
        """Wait for ready.

        Args:
            name: Stable name used to identify the value.
            process: The process value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `ManagedProcessGraph._wait_ready`. It delegates to
            `wait_for`, `sleep` while keeping intermediate state local to the owning operation.
        """
        try:
            await asyncio.wait_for(asyncio.sleep(0.02), timeout=self.startup_timeout_seconds)
        except TimeoutError as error:
            raise ManagedGraphError(f"managed process {name!r} did not become ready") from error
        if process.returncode is not None and name != "kernel":
            raise ManagedGraphError(f"managed process {name!r} exited before readiness: {process.returncode}")

    def status(self) -> dict[str, object]:
        """Return the status of the managed process graph operation.

        Returns:
            The requested `dict[str, object]` value.
        """
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
