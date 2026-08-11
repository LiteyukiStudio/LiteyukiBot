"""Async subprocess supervisor for local bot runtimes."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from yukilog import decode_child_runtime_line

from ..config import LoggingSettings
from .catalog import RuntimeCatalog
from .protocol import (
    ActionRequest,
    ActionResponse,
    AgentToolRequest,
    AgentToolResponse,
    ConfigMessage,
    ErrorMessage,
    EventAccepted,
    EventCompleted,
    EventMessage,
    EventTrace,
    Heartbeat,
    Hello,
    JsonValue,
    ProtocolVersion,
    Ready,
    Shutdown,
    Welcome,
    WireMessage,
    json_mapping,
    read_message,
    write_message,
)

EventSink = Callable[[str, dict[str, JsonValue]], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class ActionSinkResult:
    ok: bool
    data: JsonValue = None
    error: str | None = None


ActionSink = Callable[[str, dict[str, JsonValue]], Awaitable[ActionSinkResult]]


@dataclass(frozen=True, slots=True)
class AgentToolSinkResult:
    ok: bool
    data: JsonValue = None
    error: str | None = None


AgentToolSink = Callable[
    [str, str, dict[str, JsonValue], str, dict[str, JsonValue]],
    Awaitable[AgentToolSinkResult],
]


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
    secret_env: Mapping[str, str] = field(default_factory=dict)
    handshake_timeout: float = 10.0
    restart_limit: int = 5
    restart_window: float = 60.0
    ready_timeout: float = 30.0
    heartbeat_interval: float = 10.0
    stale_after: float = 30.0
    shutdown_timeout: float = 10.0
    max_inbound_events: int = 100
    agent_harness: str | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.kind:
            raise ValueError("runtime id and kind must not be empty")
        if self.restart_limit < 1 or self.restart_window <= 0:
            raise ValueError("runtime restart limits must be positive")
        if self.handshake_timeout <= 0 or self.ready_timeout <= 0 or self.shutdown_timeout <= 0:
            raise ValueError("runtime lifecycle timeouts must be positive")
        if self.heartbeat_interval <= 0 or self.stale_after <= self.heartbeat_interval:
            raise ValueError("runtime stale_after must exceed its positive heartbeat interval")
        if self.max_inbound_events < 1:
            raise ValueError("runtime max_inbound_events must be at least 1")
        if self.command is not None and (not self.command or any(not part for part in self.command)):
            raise ValueError("runtime command arguments must not be empty")
        if self.agent_harness is not None and (
            not self.agent_harness or self.agent_harness != self.agent_harness.strip()
        ):
            raise ValueError("runtime agent_harness must be a non-empty trimmed string")


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
    pending_events: dict[str, asyncio.Future[EventAccepted]] = field(default_factory=dict)
    pending_event_payloads: dict[str, dict[str, JsonValue]] = field(default_factory=dict)
    pending_event_traces: dict[str, EventTrace] = field(default_factory=dict)
    inbound_actions: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    inbound_events: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    inbound_agent_tools: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    active_delivery_contexts: dict[str, tuple[float, dict[str, JsonValue], EventTrace | None]] = field(
        default_factory=dict
    )
    protocol_version: ProtocolVersion | None = None
    capabilities: frozenset[str] = frozenset()
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    launch_count: int = 0


class RuntimeSupervisor:
    def __init__(
        self,
        *,
        logger: Any,
        event_sink: EventSink | None = None,
        action_sink: ActionSink | None = None,
        agent_tool_sink: AgentToolSink | None = None,
        secret_values: Mapping[str, str] | None = None,
    ) -> None:
        self.logger = logger
        self.event_sink = event_sink
        self.action_sink = action_sink
        self.agent_tool_sink = agent_tool_sink
        self.secret_values = dict(secret_values or {})
        self.records: dict[str, RuntimeRecord] = {}
        self._server: asyncio.Server | None = None
        self._host = "127.0.0.1"
        self._port = 0
        self._closing = False
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._logging_settings = LoggingSettings()

    def add(self, spec: RuntimeSpec) -> None:
        if spec.id in self.records:
            raise ValueError(f"duplicate runtime id: {spec.id}")
        self.records[spec.id] = RuntimeRecord(spec=spec, token=secrets.token_urlsafe(32))

    def set_agent_tool_sink(self, sink: AgentToolSink | None) -> None:
        if self._server is not None:
            raise RuntimeError("agent tool sink cannot change after runtime startup")
        self.agent_tool_sink = sink

    def set_logging_settings(self, settings: LoggingSettings) -> None:
        if self._server is not None:
            raise RuntimeError("runtime logging settings cannot change after runtime startup")
        self._logging_settings = settings

    def merge_options(self, runtime_id: str, options: Mapping[str, Any]) -> None:
        if self._server is not None:
            raise RuntimeError("runtime options cannot change after runtime startup")
        record = self.records[runtime_id]
        record.spec = replace(record.spec, options={**record.spec.options, **options})

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
            self.logger.bind(runtime=record.spec.id, component="runtime").info(
                "starting {} runtime (attempt {})", record.spec.kind, record.launch_count + 1
            )
            env = self._child_environment(record)
            env.update(
                {
                    "LITEYUKI_RUNTIME_HOST": self._host,
                    "LITEYUKI_RUNTIME_PORT": str(self._port),
                    "LITEYUKI_RUNTIME_TOKEN": record.token,
                    "LITEYUKI_RUNTIME_ID": record.spec.id,
                    "LITEYUKI_RUNTIME_KIND": record.spec.kind,
                    "LITEYUKI_RUNTIME_RESTART_COUNT": str(record.launch_count),
                    "LITEYUKI_RUNTIME_LOG_LEVEL": self._logging_settings.level,
                    "LITEYUKI_RUNTIME_PAYLOAD_MODE": self._payload_mode(record),
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
            self.logger.bind(runtime=record.spec.id, component="runtime", exit_code=exit_code).info(
                "runtime process exited"
            )
            if not record.desired or self._closing:
                record.state = RuntimeState.STOPPED
                return
            if exit_code == 0:
                record.state = RuntimeState.STOPPED
                return
            if not self._register_failure(record):
                return
            self.logger.warning("runtime {} exited with {}; restarting in {:.1f}s", record.spec.id, exit_code, delay)
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

    def _child_environment(self, record: RuntimeRecord) -> dict[str, str]:
        """Construct a child-only environment without retaining vault credentials."""

        env = os.environ.copy()
        env.pop("LITEYUKI_VAULT_PASSWORD", None)
        env.update(record.spec.env)
        for environment_name, secret_name in record.spec.secret_env.items():
            try:
                env[environment_name] = self.secret_values[secret_name]
            except KeyError as error:
                raise RuntimeError(
                    f"runtime {record.spec.id} requires unavailable secret {secret_name!r}"
                ) from error
        return env

    @staticmethod
    def _default_command(spec: RuntimeSpec) -> tuple[str, ...]:
        return RuntimeCatalog().command_for(spec.kind)

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
            record.protocol_version = message.protocol
            await self._send(
                record,
                Welcome(
                    protocol=message.protocol,
                    heartbeat_interval=record.spec.heartbeat_interval,
                ),
            )
            await self._send(record, ConfigMessage(options=json_mapping(record.spec.options)))
            await self._receive_loop(record)
        except EOFError, ConnectionError:
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
            record.capabilities = frozenset(message.capabilities)
            record.state = RuntimeState.READY
            record.ready.set()
            self.logger.bind(
                runtime=record.spec.id,
                component="runtime",
                protocol=record.protocol_version,
                capabilities=tuple(sorted(record.capabilities)),
            ).info("runtime is ready")
        elif isinstance(message, Heartbeat):
            record.last_heartbeat = time.monotonic()
        elif isinstance(message, EventMessage):
            await self._accept_child_event(record, message)
        elif isinstance(message, EventAccepted):
            event_future = record.pending_events.pop(message.correlation_id, None)
            if event_future is not None and not event_future.done():
                payload = record.pending_event_payloads.pop(message.correlation_id, None)
                if message.status == "accepted":
                    if payload is None:
                        self.logger.warning(
                            "runtime {} accepted event {} without a pending delivery context",
                            record.spec.id,
                            message.correlation_id,
                        )
                    else:
                        record.active_delivery_contexts[message.correlation_id] = (
                            time.monotonic() + 30.0,
                            payload,
                            record.pending_event_traces.pop(message.correlation_id, None),
                        )
                event_future.set_result(message)
        elif isinstance(message, EventCompleted):
            await self._accept_event_completed(record, message)
        elif isinstance(message, ActionRequest):
            await self._accept_child_action(record, message)
        elif isinstance(message, ActionResponse):
            action_future = record.pending_actions.pop(message.correlation_id, None)
            if action_future is not None and not action_future.done():
                action_future.set_result(message)
        elif isinstance(message, AgentToolRequest):
            await self._accept_agent_tool_request(record, message)
        elif isinstance(message, ErrorMessage):
            self.logger.error("runtime {} error {}: {}", record.spec.id, message.code, message.message)
        else:
            self.logger.debug("ignored runtime {} message {}", record.spec.id, message.type)

    async def _accept_event_completed(self, record: RuntimeRecord, message: EventCompleted) -> None:
        if record.protocol_version != 4 or "runtime.events.complete" not in record.capabilities:
            self.logger.warning(
                "runtime {} sent an unsupported event outcome over protocol v{}",
                record.spec.id,
                record.protocol_version,
            )
            return
        delivery = record.active_delivery_contexts.pop(message.correlation_id, None)
        if delivery is None:
            self.logger.warning(
                "runtime {} completed unknown event delivery {}",
                record.spec.id,
                message.correlation_id,
            )
            return
        _deadline, _payload, trace = delivery
        self.logger.bind(
            runtime=record.spec.id,
            component="ipc",
            correlation_id=message.correlation_id,
            trace_id=trace.trace_id if trace is not None else None,
            source_runtime_id=trace.source_runtime_id if trace is not None else None,
            source_event_id=trace.source_event_id if trace is not None else None,
            operation="event.completed",
            status=message.status,
            detail=message.detail,
        ).info("runtime event delivery {}", message.status)

    async def _accept_child_event(self, record: RuntimeRecord, message: EventMessage) -> None:
        if message.correlation_id in record.inbound_events:
            await self._send(
                record,
                EventAccepted(
                    correlation_id=message.correlation_id,
                    status="invalid",
                    detail="duplicate child event correlation id",
                ),
            )
            return
        if len(record.inbound_events) >= record.spec.max_inbound_events:
            await self._send(
                record,
                EventAccepted(
                    correlation_id=message.correlation_id,
                    status="overloaded",
                    detail="runtime inbound event capacity is exhausted",
                ),
            )
            return
        task = asyncio.create_task(
            self._execute_child_event(record, message),
            name=f"runtime-event:{record.spec.id}:{message.correlation_id}",
        )
        record.inbound_events[message.correlation_id] = task

    async def _execute_child_event(self, record: RuntimeRecord, message: EventMessage) -> None:
        detail: str | None = None
        try:
            status = "accepted" if self.event_sink is None else await self.event_sink(record.spec.id, message.payload)
            match status:
                case "accepted" | "overloaded" | "invalid":
                    normalized = status
                case _:
                    normalized = "invalid"
        except Exception as error:
            self.logger.error("runtime {} child event {} failed: {}", record.spec.id, message.correlation_id, error)
            normalized = "invalid"
            detail = "core event sink failed"
        try:
            await self._send(
                record,
                EventAccepted(
                    correlation_id=message.correlation_id,
                    status=normalized,
                    detail=detail,
                ),
            )
        except ConnectionError, RuntimeError:
            pass
        finally:
            record.inbound_events.pop(message.correlation_id, None)

    async def _accept_child_action(self, record: RuntimeRecord, request: ActionRequest) -> None:
        if record.protocol_version not in (3, 4):
            await self._reject_child_action(
                record,
                request,
                "child-originated actions require runtime protocol v3 or v4",
            )
            return
        if "runtime.actions.send" not in record.capabilities:
            await self._reject_child_action(
                record,
                request,
                "child runtime did not declare runtime.actions.send",
            )
            return
        if self.action_sink is None:
            await self._reject_child_action(record, request, "core action sink is unavailable")
            return
        if request.correlation_id in record.inbound_actions:
            await self._reject_child_action(
                record,
                request,
                f"duplicate action correlation id: {request.correlation_id}",
            )
            return

        task = asyncio.create_task(
            self._execute_child_action(record, request),
            name=f"runtime-action:{record.spec.id}:{request.correlation_id}",
        )
        record.inbound_actions[request.correlation_id] = task

    async def _execute_child_action(self, record: RuntimeRecord, request: ActionRequest) -> None:
        try:
            assert self.action_sink is not None
            result = await self.action_sink(record.spec.id, request.payload)
            response = ActionResponse(
                correlation_id=request.correlation_id,
                ok=result.ok,
                data=result.data,
                error=result.error,
            )
        except Exception as error:
            self.logger.error(
                "runtime {} child action {} failed: {}",
                record.spec.id,
                request.correlation_id,
                error,
            )
            response = ActionResponse(
                correlation_id=request.correlation_id,
                ok=False,
                error="core action sink failed",
            )
        try:
            await self._send(record, response)
        except ConnectionError, RuntimeError:
            pass
        finally:
            record.inbound_actions.pop(request.correlation_id, None)

    async def _reject_child_action(
        self,
        record: RuntimeRecord,
        request: ActionRequest,
        error: str,
    ) -> None:
        await self._send(
            record,
            ActionResponse(
                correlation_id=request.correlation_id,
                ok=False,
                error=error,
            ),
        )

    async def _accept_agent_tool_request(self, record: RuntimeRecord, request: AgentToolRequest) -> None:
        self._clear_expired_delivery_contexts(record)
        if record.protocol_version not in (3, 4):
            await self._reject_agent_tool_request(
                record, request, "agent tools require runtime protocol v3 or v4"
            )
            return
        if record.spec.agent_harness is None:
            await self._reject_agent_tool_request(record, request, "runtime is not an agent harness")
            return
        if "agent.tools.execute" not in record.capabilities:
            await self._reject_agent_tool_request(record, request, "child runtime did not declare agent.tools.execute")
            return
        delivery_context = record.active_delivery_contexts.get(request.delivery_correlation_id)
        if delivery_context is None:
            await self._reject_agent_tool_request(
                record, request, "agent tool request is not bound to an active event delivery"
            )
            return
        if self.agent_tool_sink is None:
            await self._reject_agent_tool_request(record, request, "agent tool broker is unavailable")
            return
        if request.correlation_id in record.inbound_agent_tools:
            await self._reject_agent_tool_request(
                record, request, f"duplicate agent tool correlation id: {request.correlation_id}"
            )
            return
        task = asyncio.create_task(
            self._execute_agent_tool_request(record, request),
            name=f"runtime-agent-tool:{record.spec.id}:{request.correlation_id}",
        )
        record.inbound_agent_tools[request.correlation_id] = task

    async def _execute_agent_tool_request(self, record: RuntimeRecord, request: AgentToolRequest) -> None:
        try:
            assert self.agent_tool_sink is not None
            _deadline, payload, _trace = record.active_delivery_contexts[request.delivery_correlation_id]
            result = await self.agent_tool_sink(
                record.spec.id,
                request.delivery_correlation_id,
                payload,
                request.tool_id,
                request.arguments,
            )
            response = AgentToolResponse(
                correlation_id=request.correlation_id,
                ok=result.ok,
                data=result.data,
                error=result.error,
            )
        except Exception as error:
            self.logger.error("runtime {} agent tool {} failed: {}", record.spec.id, request.tool_id, error)
            response = AgentToolResponse(
                correlation_id=request.correlation_id,
                ok=False,
                error="agent tool broker failed",
            )
        try:
            await self._send(record, response)
        except ConnectionError, RuntimeError:
            pass
        finally:
            record.inbound_agent_tools.pop(request.correlation_id, None)

    async def _reject_agent_tool_request(
        self,
        record: RuntimeRecord,
        request: AgentToolRequest,
        error: str,
    ) -> None:
        await self._send(
            record,
            AgentToolResponse(
                correlation_id=request.correlation_id,
                ok=False,
                error=error,
            ),
        )

    @staticmethod
    def _clear_expired_delivery_contexts(record: RuntimeRecord) -> None:
        now = time.monotonic()
        for correlation_id, (deadline, _payload, _trace) in tuple(record.active_delivery_contexts.items()):
            if deadline <= now:
                record.active_delivery_contexts.pop(correlation_id, None)

    async def execute_action(
        self,
        runtime_id: str,
        correlation_id: str,
        payload: Mapping[str, Any],
        timeout_seconds: float = 30.0,
    ) -> ActionResponse:
        if timeout_seconds <= 0:
            raise ValueError("runtime action timeout must be positive")
        record = self.records[runtime_id]
        if record.state is not RuntimeState.READY:
            raise RuntimeError(f"runtime {runtime_id} is not ready")
        if correlation_id in record.pending_actions:
            raise ValueError(f"duplicate action correlation id: {correlation_id}")
        future: asyncio.Future[ActionResponse] = asyncio.get_running_loop().create_future()
        record.pending_actions[correlation_id] = future
        try:
            self._log_payload(record, "action.request", correlation_id, payload)
            await self._send(
                record,
                ActionRequest(correlation_id=correlation_id, payload=json_mapping(payload)),
            )
            async with asyncio.timeout(timeout_seconds):
                response = await future
            self._log_payload(
                record,
                "action.response",
                correlation_id,
                {"ok": response.ok, "data": response.data, "error": response.error},
            )
            return response
        finally:
            record.pending_actions.pop(correlation_id, None)

    async def dispatch_event(
        self,
        runtime_id: str,
        correlation_id: str,
        payload: Mapping[str, Any],
        timeout_seconds: float = 30.0,
    ) -> EventAccepted:
        if timeout_seconds <= 0:
            raise ValueError("runtime event timeout must be positive")
        record = self.records[runtime_id]
        if record.state is not RuntimeState.READY:
            raise RuntimeError(f"runtime {runtime_id} is not ready")
        if record.protocol_version not in (2, 3, 4):
            raise RuntimeError(f"runtime {runtime_id} did not negotiate protocol v2, v3, or v4")
        if "runtime.events.receive" not in record.capabilities:
            raise RuntimeError(f"runtime {runtime_id} does not accept core events")
        if correlation_id in record.pending_events:
            raise ValueError(f"duplicate event correlation id: {correlation_id}")
        future: asyncio.Future[EventAccepted] = asyncio.get_running_loop().create_future()
        record.pending_events[correlation_id] = future
        record.pending_event_payloads[correlation_id] = json_mapping(payload)
        trace = self._event_trace(record, correlation_id, record.pending_event_payloads[correlation_id])
        if record.protocol_version == 4:
            record.pending_event_traces[correlation_id] = trace
        try:
            self._log_payload(record, "event.dispatch", correlation_id, payload, trace=trace)
            await self._send(
                record,
                EventMessage(
                    correlation_id=correlation_id,
                    payload=record.pending_event_payloads[correlation_id],
                    trace=trace if record.protocol_version == 4 else None,
                ),
            )
            async with asyncio.timeout(timeout_seconds):
                accepted = await future
            self._log_payload(
                record,
                "event.accepted",
                correlation_id,
                {"status": accepted.status, "detail": accepted.detail},
                trace=trace,
            )
            return accepted
        finally:
            record.pending_events.pop(correlation_id, None)
            record.pending_event_payloads.pop(correlation_id, None)
            record.pending_event_traces.pop(correlation_id, None)

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
            except ConnectionError, RuntimeError:
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
        record.protocol_version = None
        record.capabilities = frozenset()
        record.active_delivery_contexts.clear()
        for action_future in record.pending_actions.values():
            if not action_future.done():
                action_future.set_exception(ConnectionError(f"runtime {record.spec.id} disconnected"))
        record.pending_actions.clear()
        for event_future in record.pending_events.values():
            if not event_future.done():
                event_future.set_exception(ConnectionError(f"runtime {record.spec.id} disconnected"))
        record.pending_events.clear()
        record.pending_event_payloads.clear()
        record.pending_event_traces.clear()
        inbound_actions = tuple(record.inbound_actions.values())
        record.inbound_actions.clear()
        for task in inbound_actions:
            task.cancel()
        if inbound_actions:
            await asyncio.gather(*inbound_actions, return_exceptions=True)
        inbound_events = tuple(record.inbound_events.values())
        record.inbound_events.clear()
        for task in inbound_events:
            task.cancel()
        if inbound_events:
            await asyncio.gather(*inbound_events, return_exceptions=True)
        inbound_agent_tools = tuple(record.inbound_agent_tools.values())
        record.inbound_agent_tools.clear()
        for task in inbound_agent_tools:
            task.cancel()
        if inbound_agent_tools:
            await asyncio.gather(*inbound_agent_tools, return_exceptions=True)
        if writer is not None:
            writer.close()
            await writer.wait_closed()

    async def _capture_output(self, record: RuntimeRecord, stream: asyncio.StreamReader, channel: str) -> None:
        logger = self.logger.bind(
            runtime=record.spec.id,
            component="runtime",
            stream=channel,
            upstream=record.spec.kind,
        )
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
            for key in (
                "component",
                "plugin",
                "event_id",
                "bot_id",
                "correlation_id",
                "action_id",
                "trace_id",
                "source_runtime_id",
                "source_event_id",
                "upstream",
                "upstream_category",
            )
            if payload.get(key) is not None
        }
        extra = payload.get("extra")
        if isinstance(extra, Mapping):
            context.update({str(key): value for key, value in extra.items()})
        child_logger = logger.bind(**context)
        level = str(payload.get("level", "INFO")).lower()
        method = getattr(child_logger, level, child_logger.info)
        method("{}", str(payload.get("message", "")))

    def _payload_mode(self, record: RuntimeRecord) -> str:
        if record.spec.id in self._logging_settings.payload_exclude_runtimes:
            return "metadata"
        return self._logging_settings.payload_mode

    def _log_payload(
        self,
        record: RuntimeRecord,
        operation: str,
        correlation_id: str,
        payload: Mapping[str, Any],
        *,
        trace: EventTrace | None = None,
    ) -> None:
        serialized = json_mapping(payload)
        context: dict[str, Any] = {
            "runtime": record.spec.id,
            "component": "ipc",
            "correlation_id": correlation_id,
            "operation": operation,
            "payload_keys": tuple(sorted(serialized)),
            "payload_bytes": len(json.dumps(serialized, ensure_ascii=True, separators=(",", ":"))),
        }
        if trace is not None:
            context.update(
                trace_id=trace.trace_id,
                source_runtime_id=trace.source_runtime_id,
                source_event_id=trace.source_event_id,
            )
        if self._payload_mode(record) == "full":
            context["payload"] = serialized
        self.logger.bind(**context).debug("runtime IPC {}", operation)

    @staticmethod
    def _event_trace(
        record: RuntimeRecord,
        correlation_id: str,
        payload: Mapping[str, JsonValue],
    ) -> EventTrace:
        source_runtime_id = payload.get("runtime_id")
        source_event_id = payload.get("id")
        if (
            isinstance(source_runtime_id, str)
            and source_runtime_id
            and isinstance(source_event_id, str)
            and source_event_id
        ):
            return EventTrace(
                trace_id=source_event_id,
                source_runtime_id=source_runtime_id,
                source_event_id=source_event_id,
            )
        return EventTrace(
            trace_id=correlation_id,
            source_runtime_id=record.spec.id,
            source_event_id=correlation_id,
        )

    async def _watch_heartbeats(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            now = time.monotonic()
            for record in self.records.values():
                if record.state is RuntimeState.READY and now - record.last_heartbeat > record.spec.stale_after:
                    self.logger.error("runtime {} heartbeat timed out", record.spec.id)
                    if record.process is not None:
                        record.process.terminate()
