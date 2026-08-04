"""Async subprocess supervisor for local bot runtimes."""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from yukilog import decode_child_runtime_line

from .protocol import (
    ActionRequest,
    ActionResponse,
    ConfigMessage,
    ErrorMessage,
    EventAccepted,
    EventMessage,
    Heartbeat,
    Hello,
    JsonValue,
    Ready,
    Shutdown,
    Welcome,
    WireMessage,
    json_mapping,
    read_message,
    write_message,
)

EventSink = Callable[[str, dict[str, JsonValue]], Awaitable[str]]


class RuntimeState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RuntimeSpec:
    id: str
    kind: str
    options: Mapping[str, Any] = field(default_factory=dict)
    command: Sequence[str] | None = None
    working_directory: str | Path | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    handshake_timeout: float = 10.0
    restart_limit: int = 5
    restart_window: float = 60.0
    ready_timeout: float = 30.0
    heartbeat_interval: float = 10.0
    stale_after: float = 30.0
    shutdown_timeout: float = 10.0

    def __post_init__(self) -> None:
        if not self.id or not self.kind:
            raise ValueError("runtime id and kind must not be empty")
        if self.restart_limit < 1 or self.restart_window <= 0:
            raise ValueError("runtime restart limits must be positive")
        if self.handshake_timeout <= 0 or self.ready_timeout <= 0 or self.shutdown_timeout <= 0:
            raise ValueError("runtime lifecycle timeouts must be positive")
        if self.heartbeat_interval <= 0 or self.stale_after <= self.heartbeat_interval:
            raise ValueError("runtime stale_after must exceed its positive heartbeat interval")


@dataclass(slots=True)
class RuntimeRecord:
    spec: RuntimeSpec
    token: str
    state: RuntimeState = RuntimeState.STOPPED
    process: asyncio.subprocess.Process | None = None
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    connected: asyncio.Event = field(default_factory=asyncio.Event)
    desired: bool = True
    last_heartbeat: float = field(default_factory=time.monotonic)
    failures: deque[float] = field(default_factory=deque)
    runner: asyncio.Task[None] | None = None
    output_tasks: tuple[asyncio.Task[None], ...] = ()
    pending_actions: dict[str, asyncio.Future[ActionResponse]] = field(default_factory=dict)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    launch_count: int = 0


class RuntimeSupervisor:
    def __init__(self, *, logger: Any, event_sink: EventSink | None = None) -> None:
        self.logger = logger
        self.event_sink = event_sink
        self.records: dict[str, RuntimeRecord] = {}
        self._server: asyncio.Server | None = None
        self._host = "127.0.0.1"
        self._port = 0
        self._closing = False
        self._heartbeat_task: asyncio.Task[None] | None = None

    def add(self, spec: RuntimeSpec) -> None:
        if spec.id in self.records:
            raise ValueError(f"duplicate runtime id: {spec.id}")
        self.records[spec.id] = RuntimeRecord(spec=spec, token=secrets.token_urlsafe(32))

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._accept, self._host, 0)
        socket = self._server.sockets[0]
        self._port = int(socket.getsockname()[1])
        self._heartbeat_task = asyncio.create_task(self._watch_heartbeats(), name="runtime-heartbeats")
        for record in self.records.values():
            record.desired = True
            record.runner = asyncio.create_task(self._run(record), name=f"runtime:{record.spec.id}")
        try:
            async with asyncio.timeout(max((r.spec.ready_timeout for r in self.records.values()), default=0.1)):
                await asyncio.gather(*(self._wait_until_ready(record) for record in self.records.values()))
        except TimeoutError:
            failed = [record.spec.id for record in self.records.values() if not record.ready.is_set()]
            await self.stop()
            raise TimeoutError(f"runtimes did not become ready: {', '.join(failed)}") from None
        except BaseException:
            await self.stop()
            raise

    @staticmethod
    async def _wait_until_ready(record: RuntimeRecord) -> None:
        if record.runner is None:
            raise RuntimeError(f"runtime {record.spec.id} has no supervisor task")
        ready = asyncio.create_task(record.ready.wait(), name=f"runtime-ready:{record.spec.id}")
        done, _pending = await asyncio.wait((ready, record.runner), return_when=asyncio.FIRST_COMPLETED)
        if ready in done and ready.result():
            return
        ready.cancel()
        await asyncio.gather(ready, return_exceptions=True)
        error = record.runner.exception()
        if error is not None:
            raise RuntimeError(f"runtime {record.spec.id} failed before becoming ready") from error
        if record.state is RuntimeState.FAILED:
            raise RuntimeError(f"runtime {record.spec.id} failed before becoming ready")
        raise RuntimeError(f"runtime {record.spec.id} stopped before becoming ready")

    async def _run(self, record: RuntimeRecord) -> None:
        delay = 1.0
        while record.desired and not self._closing:
            record.state = RuntimeState.STARTING
            record.ready.clear()
            record.connected.clear()
            command = list(record.spec.command or self._default_command(record.spec))
            env = os.environ.copy()
            env.update(record.spec.env)
            env.update(
                {
                    "LITEYUKI_RUNTIME_HOST": self._host,
                    "LITEYUKI_RUNTIME_PORT": str(self._port),
                    "LITEYUKI_RUNTIME_TOKEN": record.token,
                    "LITEYUKI_RUNTIME_ID": record.spec.id,
                    "LITEYUKI_RUNTIME_KIND": record.spec.kind,
                    "LITEYUKI_RUNTIME_RESTART_COUNT": str(record.launch_count),
                }
            )
            record.launch_count += 1
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=record.spec.working_directory,
                    env=env,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as error:
                self.logger.error("runtime {} could not start: {}", record.spec.id, error)
                if not self._register_failure(record):
                    return
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)
                continue
            record.process = process
            assert process.stdout is not None
            assert process.stderr is not None
            record.output_tasks = (
                asyncio.create_task(self._capture_output(record, process.stdout, "stdout")),
                asyncio.create_task(self._capture_output(record, process.stderr, "stderr")),
            )
            exit_code = await process.wait()
            await asyncio.gather(*record.output_tasks, return_exceptions=True)
            await self._disconnect(record)
            record.process = None
            if not record.desired or self._closing:
                record.state = RuntimeState.STOPPED
                return
            if exit_code == 0:
                record.state = RuntimeState.STOPPED
                return
            if not self._register_failure(record):
                return
            self.logger.warning(
                "runtime {} exited with {}; restarting in {:.1f}s", record.spec.id, exit_code, delay
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)

    @staticmethod
    def _register_failure(record: RuntimeRecord) -> bool:
        now = time.monotonic()
        record.failures.append(now)
        while record.failures and now - record.failures[0] > record.spec.restart_window:
            record.failures.popleft()
        if len(record.failures) >= record.spec.restart_limit:
            record.state = RuntimeState.FAILED
            return False
        return True

    @staticmethod
    def _default_command(spec: RuntimeSpec) -> tuple[str, ...]:
        return (sys.executable, "-m", "liteyukibot.runtime", "--kind", spec.kind)

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        record: RuntimeRecord | None = None
        try:
            handshake_timeout = max(
                (candidate.spec.handshake_timeout for candidate in self.records.values()),
                default=10.0,
            )
            async with asyncio.timeout(handshake_timeout):
                message = await read_message(reader)
            if not isinstance(message, Hello):
                raise ValueError("first runtime message must be hello")
            record = self.records.get(message.runtime_id)
            if record is None or not secrets.compare_digest(record.token, message.token):
                raise ValueError("runtime authentication failed")
            if message.kind != record.spec.kind or record.writer is not None:
                raise ValueError("runtime identity mismatch or duplicate connection")
            record.reader = reader
            record.writer = writer
            record.connected.set()
            record.last_heartbeat = time.monotonic()
            await self._send(record, Welcome(heartbeat_interval=record.spec.heartbeat_interval))
            await self._send(record, ConfigMessage(options=json_mapping(record.spec.options)))
            await self._receive_loop(record)
        except (EOFError, ConnectionError):
            pass
        except BaseException as exc:
            self.logger.error("runtime connection rejected: {}", exc)
        finally:
            if record is not None and record.writer is writer:
                await self._disconnect(record)
            else:
                writer.close()
                await writer.wait_closed()

    async def _receive_loop(self, record: RuntimeRecord) -> None:
        assert record.reader is not None
        while True:
            message = await read_message(record.reader)
            await self._handle_message(record, message)

    async def _handle_message(self, record: RuntimeRecord, message: WireMessage) -> None:
        if isinstance(message, Ready):
            record.state = RuntimeState.READY
            record.ready.set()
        elif isinstance(message, Heartbeat):
            record.last_heartbeat = time.monotonic()
        elif isinstance(message, EventMessage):
            status = "accepted"
            if self.event_sink is not None:
                status = await self.event_sink(record.spec.id, message.payload)
            match status:
                case "accepted" | "overloaded" | "invalid":
                    normalized = status
                case _:
                    normalized = "invalid"
            await self._send(
                record,
                EventAccepted(correlation_id=message.correlation_id, status=normalized),
            )
        elif isinstance(message, ActionResponse):
            future = record.pending_actions.pop(message.correlation_id, None)
            if future is not None and not future.done():
                future.set_result(message)
        elif isinstance(message, ErrorMessage):
            self.logger.error("runtime {} error {}: {}", record.spec.id, message.code, message.message)
        else:
            self.logger.debug("ignored runtime {} message {}", record.spec.id, message.type)

    async def execute_action(
        self,
        runtime_id: str,
        correlation_id: str,
        payload: Mapping[str, Any],
        timeout_seconds: float = 30.0,
    ) -> ActionResponse:
        record = self.records[runtime_id]
        if record.state is not RuntimeState.READY:
            raise RuntimeError(f"runtime {runtime_id} is not ready")
        future: asyncio.Future[ActionResponse] = asyncio.get_running_loop().create_future()
        record.pending_actions[correlation_id] = future
        try:
            await self._send(
                record,
                ActionRequest(correlation_id=correlation_id, payload=json_mapping(payload)),
            )
            async with asyncio.timeout(timeout_seconds):
                return await future
        finally:
            record.pending_actions.pop(correlation_id, None)

    async def restart(self, runtime_id: str) -> None:
        record = self.records[runtime_id]
        record.failures.clear()
        process = record.process
        if process is None:
            record.desired = False
            if record.runner is not None and not record.runner.done():
                record.runner.cancel()
                await asyncio.gather(record.runner, return_exceptions=True)
            record.desired = True
            record.runner = asyncio.create_task(self._run(record), name=f"runtime:{runtime_id}")
            async with asyncio.timeout(record.spec.ready_timeout):
                await record.ready.wait()
            return
        await self._request_stop(record, "restart")
        if record.runner is not None:
            await record.runner
        record.desired = True
        record.runner = asyncio.create_task(self._run(record), name=f"runtime:{runtime_id}")
        async with asyncio.timeout(record.spec.ready_timeout):
            await record.ready.wait()

    async def stop(self) -> None:
        self._closing = True
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            await asyncio.gather(self._heartbeat_task, return_exceptions=True)
        await asyncio.gather(
            *(self._request_stop(record, "application shutdown") for record in self.records.values()),
            return_exceptions=True,
        )
        runners = [record.runner for record in self.records.values() if record.runner is not None]
        if runners:
            await asyncio.gather(*runners, return_exceptions=True)
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _request_stop(self, record: RuntimeRecord, reason: str) -> None:
        record.desired = False
        record.state = RuntimeState.STOPPING
        if record.writer is not None:
            try:
                await self._send(record, Shutdown(reason=reason))
            except (ConnectionError, RuntimeError):
                pass
        process = record.process
        if process is None:
            record.state = RuntimeState.STOPPED
            runner = record.runner
            if runner is not None and runner is not asyncio.current_task() and not runner.done():
                runner.cancel()
                await asyncio.gather(runner, return_exceptions=True)
            return
        try:
            async with asyncio.timeout(record.spec.shutdown_timeout):
                await process.wait()
        except TimeoutError:
            process.terminate()
            try:
                async with asyncio.timeout(5.0):
                    await process.wait()
            except TimeoutError:
                process.kill()
                await process.wait()

    async def _send(self, record: RuntimeRecord, message: WireMessage) -> None:
        if record.writer is None:
            raise ConnectionError(f"runtime {record.spec.id} is not connected")
        async with record.send_lock:
            await write_message(record.writer, message)

    async def _disconnect(self, record: RuntimeRecord) -> None:
        writer, record.writer = record.writer, None
        record.reader = None
        record.connected.clear()
        record.ready.clear()
        for future in record.pending_actions.values():
            if not future.done():
                future.set_exception(ConnectionError(f"runtime {record.spec.id} disconnected"))
        record.pending_actions.clear()
        if writer is not None:
            writer.close()
            await writer.wait_closed()

    async def _capture_output(
        self, record: RuntimeRecord, stream: asyncio.StreamReader, channel: str
    ) -> None:
        logger = self.logger.bind(runtime=record.spec.id, component="runtime", stream=channel)
        while line := await stream.readline():
            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            structured = decode_child_runtime_line(text)
            if structured is not None:
                self._emit_structured_output(logger, structured)
                continue
            if channel == "stderr":
                logger.error("{}", text)
            else:
                logger.info("{}", text)

    @staticmethod
    def _emit_structured_output(logger: Any, payload: Mapping[str, object]) -> None:
        context = {
            key: payload[key]
            for key in ("component", "plugin", "event_id", "bot_id")
            if payload.get(key) is not None
        }
        extra = payload.get("extra")
        if isinstance(extra, Mapping):
            context.update({str(key): value for key, value in extra.items()})
        child_logger = logger.bind(**context)
        level = str(payload.get("level", "INFO")).lower()
        method = getattr(child_logger, level, child_logger.info)
        method("{}", str(payload.get("message", "")))

    async def _watch_heartbeats(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            now = time.monotonic()
            for record in self.records.values():
                if record.state is RuntimeState.READY and now - record.last_heartbeat > record.spec.stale_after:
                    self.logger.error("runtime {} heartbeat timed out", record.spec.id)
                    if record.process is not None:
                        record.process.terminate()
