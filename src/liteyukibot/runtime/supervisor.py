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
from typing import Any, Literal

import zmq.asyncio
from yukilog import decode_child_runtime_line

from ..config import LoggingSettings, LyipSettings
from ..lyip import LyipError, LyipFrame, LyipLane, LyipOfferResult, ZmqLyipRouter
from .catalog import RuntimeCatalog
from .ledger import (
    ActionClaimState,
    DeliverySnapshot,
    DeliveryTerminalReason,
    DeliveryTransitionError,
    EventLedger,
    EventLedgerError,
    EventProvenance,
    RouteSnapshot,
)
from .lyip import decode_runtime_message, encode_runtime_message
from .protocol import (
    ActionRequest,
    ActionResponse,
    AgentToolRequest,
    AgentToolResponse,
    ConfigMessage,
    ControlRequest,
    ControlResponse,
    ErrorMessage,
    EventAccepted,
    EventCompleted,
    EventIngress,
    EventMessage,
    EventSourceProvenance,
    Heartbeat,
    Hello,
    JsonValue,
    ManagementRequest,
    ManagementResponse,
    ProtocolVersion,
    Ready,
    Shutdown,
    Welcome,
    WireMessage,
    json_mapping,
)

EventSink = Callable[[str, str, dict[str, JsonValue]], Awaitable[str]]
RuntimeOutputSink = Callable[[str, Literal["stdout", "stderr"], str], None]
DeliveryCompletionSink = Callable[[str, EventCompleted], Awaitable[None]]
AgentToolCatalogProvider = Callable[[DeliverySnapshot], Mapping[str, Any] | None]


@dataclass(frozen=True, slots=True)
class ActionSinkResult:
    ok: bool
    data: JsonValue = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ActionProvenance:
    """Kernel-validated source event context for a child side effect."""

    delivery_id: str
    source_runtime_id: str
    source_event_id: str
    event_payload: dict[str, JsonValue]


ActionSink = Callable[[str, dict[str, JsonValue], ActionProvenance | None], Awaitable[ActionSinkResult]]


@dataclass(frozen=True, slots=True)
class AgentToolSinkResult:
    ok: bool
    data: JsonValue = None
    error: str | None = None


AgentToolSink = Callable[
    [str, str, dict[str, JsonValue], str, dict[str, JsonValue]],
    Awaitable[AgentToolSinkResult],
]
ManagementSink = Callable[[str, str], Awaitable[tuple[bool, str, JsonValue, str | None]]]


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
    router: ZmqLyipRouter | None = None
    expected_identity: bytes | None = None
    identity: bytes | None = None
    generation: int = 0
    lease_id: str | None = None
    receive_tasks: tuple[asyncio.Task[None], ...] = ()
    handshake_task: asyncio.Task[None] | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    connected: asyncio.Event = field(default_factory=asyncio.Event)
    desired: bool = True
    last_heartbeat: float = field(default_factory=time.monotonic)
    failures: deque[float] = field(default_factory=deque)
    runner: asyncio.Task[None] | None = None
    output_tasks: tuple[asyncio.Task[None], ...] = ()
    pending_actions: dict[str, asyncio.Future[ActionResponse]] = field(default_factory=dict)
    pending_controls: dict[str, asyncio.Future[ControlResponse]] = field(default_factory=dict)
    inbound_actions: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    inbound_events: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    inbound_agent_tools: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    inbound_management: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    protocol_version: ProtocolVersion | None = None
    capabilities: frozenset[str] = frozenset()
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    send_sequences: dict[LyipLane, int] = field(
        default_factory=lambda: {LyipLane.BUSINESS: 0, LyipLane.CONTROL: 0}
    )
    launch_count: int = 0


class RuntimeSupervisor:
    def __init__(
        self,
        *,
        logger: Any,
        event_sink: EventSink | None = None,
        action_sink: ActionSink | None = None,
        agent_tool_sink: AgentToolSink | None = None,
        management_sink: ManagementSink | None = None,
        output_sink: RuntimeOutputSink | None = None,
        delivery_completion_sink: DeliveryCompletionSink | None = None,
        secret_values: Mapping[str, str] | None = None,
        lyip_settings: LyipSettings | None = None,
        ledger: EventLedger | None = None,
        delivery_timeout_seconds: float = 30.0,
        agent_tool_catalog_provider: AgentToolCatalogProvider | None = None,
    ) -> None:
        self.logger = logger
        self.event_sink = event_sink
        self.action_sink = action_sink
        self.agent_tool_sink = agent_tool_sink
        self.management_sink = management_sink
        self.output_sink = output_sink
        self.delivery_completion_sink = delivery_completion_sink
        self.secret_values = dict(secret_values or {})
        self._lyip_settings = lyip_settings or LyipSettings()
        if delivery_timeout_seconds <= 0:
            raise ValueError("delivery timeout must be positive")
        self.ledger = ledger or EventLedger()
        self._delivery_timeout_seconds = delivery_timeout_seconds
        self._agent_tool_catalog_provider = agent_tool_catalog_provider
        self.records: dict[str, RuntimeRecord] = {}
        self._transport_started = False
        self._zmq_context = zmq.asyncio.Context.instance()
        self._closing = False
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._logging_settings = LoggingSettings()

    def add(self, spec: RuntimeSpec) -> None:
        if spec.id in self.records:
            raise ValueError(f"duplicate runtime id: {spec.id}")
        self.records[spec.id] = RuntimeRecord(spec=spec, token=secrets.token_urlsafe(32))

    def set_agent_tool_sink(self, sink: AgentToolSink | None) -> None:
        if self._transport_started:
            raise RuntimeError("agent tool sink cannot change after runtime startup")
        self.agent_tool_sink = sink

    def set_management_sink(self, sink: ManagementSink | None) -> None:
        if self._transport_started:
            raise RuntimeError("management sink cannot change after runtime startup")
        self.management_sink = sink

    def set_logging_settings(self, settings: LoggingSettings) -> None:
        if self._transport_started:
            raise RuntimeError("runtime logging settings cannot change after runtime startup")
        self._logging_settings = settings

    def merge_options(self, runtime_id: str, options: Mapping[str, Any]) -> None:
        if self._transport_started:
            raise RuntimeError("runtime options cannot change after runtime startup")
        record = self.records[runtime_id]
        record.spec = replace(record.spec, options={**record.spec.options, **options})

    def health(self) -> dict[str, dict[str, object]]:
        """Return redacted runtime liveness and IPC pressure for local control planes."""

        now = time.monotonic()
        snapshots: dict[str, dict[str, object]] = {}
        for runtime_id, record in self.records.items():
            failures = sum(now - failure <= record.spec.restart_window for failure in record.failures)
            snapshots[runtime_id] = {
                "kind": record.spec.kind,
                "state": record.state.value,
                "connected": record.connected.is_set(),
                "protocol": record.protocol_version,
                "capabilities": tuple(sorted(record.capabilities)),
                "launch_count": record.launch_count,
                "heartbeat_age_seconds": (
                    max(0.0, now - record.last_heartbeat) if record.connected.is_set() else None
                ),
                "failures_in_window": failures,
                "pending_actions": len(record.pending_actions),
                "pending_controls": len(record.pending_controls),
                "inbound_actions": len(record.inbound_actions),
                "inbound_events": len(record.inbound_events),
                "inbound_agent_tools": len(record.inbound_agent_tools),
                "inbound_management": len(record.inbound_management),
                "ledger_active_events": self.ledger.active_count,
                "ledger_terminal_events": self.ledger.terminal_count,
            }
        return snapshots

    async def start(self) -> None:
        self._transport_started = True
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
            self._prepare_transport(record)
            try:
                env = self._child_environment(record)
            except BaseException:
                await self._disconnect(record)
                raise
            assert record.router is not None
            assert record.lease_id is not None
            assert record.expected_identity is not None
            env.update(
                {
                    "LITEYUKI_LYIP_BUSINESS_ENDPOINT": record.router.endpoints[LyipLane.BUSINESS],
                    "LITEYUKI_LYIP_CONTROL_ENDPOINT": record.router.endpoints[LyipLane.CONTROL],
                    "LITEYUKI_LYIP_GENERATION": str(record.generation),
                    "LITEYUKI_LYIP_LEASE_ID": record.lease_id,
                    "LITEYUKI_LYIP_IDENTITY": record.expected_identity.decode("ascii"),
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
                    await self._disconnect(record)
                    return
                await self._disconnect(record)
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

    def _prepare_transport(self, record: RuntimeRecord) -> None:
        if record.router is not None:
            raise RuntimeError(f"runtime {record.spec.id} already has an active LYIP transport")
        record.generation += 1
        record.lease_id = secrets.token_urlsafe(32)
        record.expected_identity = secrets.token_urlsafe(32).encode("ascii")
        record.identity = None
        record.send_sequences = {LyipLane.BUSINESS: 0, LyipLane.CONTROL: 0}
        resolution = self._lyip_settings.resolve_link(record.spec.id)
        if resolution.backend == "shm":
            raise RuntimeError("LYIP native shared-memory backend is unavailable for this runtime lifecycle")
        record.router = ZmqLyipRouter(
            context=self._zmq_context,
            endpoint="tcp://127.0.0.1:*",
            generation=record.generation,
            business_hwm=resolution.capacity.zmq_hwm,
            control_hwm=resolution.capacity.zmq_hwm,
        )
        record.receive_tasks = tuple(
            asyncio.create_task(
                self._receive_loop(record, lane),
                name=f"runtime-lyip:{record.spec.id}:{lane.value}",
            )
            for lane in LyipLane
        )
        record.handshake_task = asyncio.create_task(
            self._watch_handshake(record, record.generation),
            name=f"runtime-handshake:{record.spec.id}:{record.generation}",
        )

    async def _watch_handshake(self, record: RuntimeRecord, generation: int) -> None:
        await asyncio.sleep(record.spec.handshake_timeout)
        if record.generation == generation and record.identity is None and record.process is not None:
            self.logger.error("runtime {} did not complete its LYIP handshake", record.spec.id)
            record.process.terminate()

    async def _receive_loop(self, record: RuntimeRecord, lane: LyipLane) -> None:
        while True:
            router = record.router
            if router is None:
                return
            try:
                identity, frame = await router.receive(lane)
                await self._receive_frame(record, lane, identity, frame)
            except asyncio.CancelledError:
                raise
            except LyipError as error:
                self.logger.warning("runtime {} LYIP frame rejected: {}", record.spec.id, error)
            except Exception as error:
                self.logger.error("runtime {} LYIP receiver failed: {}", record.spec.id, error)

    async def _receive_frame(
        self,
        record: RuntimeRecord,
        lane: LyipLane,
        identity: bytes,
        frame: LyipFrame,
    ) -> None:
        if record.expected_identity is None or not secrets.compare_digest(identity, record.expected_identity):
            raise LyipError("LYIP identity does not match the current runtime launch")
        if record.lease_id is None or not secrets.compare_digest(frame.lease_id, record.lease_id):
            raise LyipError("LYIP lease does not match the current runtime launch")
        if frame.stream_id != self._inbound_stream_id(record, lane):
            raise LyipError("LYIP frame does not belong to the runtime lane stream")
        message = decode_runtime_message(frame)
        if record.identity is None:
            if lane is not LyipLane.CONTROL or not isinstance(message, Hello):
                raise LyipError("first runtime LYIP frame must be a control hello")
            if message.runtime_id != record.spec.id or not secrets.compare_digest(record.token, message.token):
                raise LyipError("runtime authentication failed")
            if message.kind != record.spec.kind:
                raise LyipError("runtime identity mismatch")
            if message.protocol != 6:
                raise LyipError("runtime must negotiate protocol v6")
            record.identity = identity
            record.connected.set()
            record.last_heartbeat = time.monotonic()
            record.protocol_version = message.protocol
            await self._send(
                record,
                Welcome(protocol=message.protocol, heartbeat_interval=record.spec.heartbeat_interval),
            )
            await self._send(record, ConfigMessage(options=json_mapping(record.spec.options)))
            return
        if not secrets.compare_digest(identity, record.identity):
            raise LyipError("LYIP identity changed during runtime launch")
        if isinstance(message, Hello):
            raise LyipError("duplicate LYIP hello")
        await self._handle_message(record, message)

    @staticmethod
    def _inbound_stream_id(record: RuntimeRecord, lane: LyipLane) -> str:
        return f"runtime:{record.spec.id}:{lane.value}"

    @staticmethod
    def _outbound_stream_id(record: RuntimeRecord, lane: LyipLane) -> str:
        return f"kernel:{record.spec.id}:{lane.value}"

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
        elif isinstance(message, EventIngress):
            await self._accept_child_event(record, message)
        elif isinstance(message, EventMessage):
            raise LyipError("child runtimes must submit EventIngress, not EventMessage")
        elif isinstance(message, EventAccepted):
            await self._accept_event_accepted(record, message)
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
        elif isinstance(message, ControlResponse):
            control_future = record.pending_controls.pop(message.correlation_id, None)
            if control_future is not None and not control_future.done():
                control_future.set_result(message)
        elif isinstance(message, ManagementRequest):
            await self._accept_management_request(record, message)
        elif isinstance(message, ErrorMessage):
            self.logger.error("runtime {} error {}: {}", record.spec.id, message.code, message.message)
        else:
            self.logger.debug("ignored runtime {} message {}", record.spec.id, message.type)

    async def _accept_event_accepted(self, record: RuntimeRecord, message: EventAccepted) -> None:
        if record.protocol_version != 6 or "runtime.events.receive" not in record.capabilities:
            self.logger.warning(
                "runtime {} sent an unsupported event acceptance over protocol v{}",
                record.spec.id,
                record.protocol_version,
            )
            return
        try:
            snapshot = self._find_delivery(message.delivery_id)
            if snapshot.route.target_runtime_id != record.spec.id:
                raise DeliveryTransitionError("delivery belongs to another runtime")
            assert snapshot.lease_id is not None
            if message.status == "accepted":
                self.ledger.accept_delivery(snapshot.delivery_id, snapshot.lease_id)
                self.ledger.activate_delivery(snapshot.delivery_id, snapshot.lease_id)
            else:
                reason = (
                    DeliveryTerminalReason.OVERLOADED
                    if message.status == "overloaded"
                    else DeliveryTerminalReason.RUNTIME_REJECTED
                )
                self.ledger.fail_delivery(snapshot.delivery_id, reason, lease_id=snapshot.lease_id)
        except EventLedgerError as error:
            self.logger.warning(
                "runtime {} accepted invalid delivery {}: {}",
                record.spec.id,
                message.delivery_id,
                error,
            )
        await self._schedule_ready_offers()

    async def _accept_event_completed(self, record: RuntimeRecord, message: EventCompleted) -> None:
        if record.protocol_version != 6 or "runtime.events.complete" not in record.capabilities:
            self.logger.warning("runtime {} sent an unsupported event outcome", record.spec.id)
            return
        try:
            snapshot = self._find_delivery(message.delivery_id)
            if snapshot.route.target_runtime_id != record.spec.id:
                raise DeliveryTransitionError("delivery belongs to another runtime")
            assert snapshot.lease_id is not None
            if message.status == "completed":
                self.ledger.complete_delivery(snapshot.delivery_id, snapshot.lease_id)
            else:
                self.ledger.fail_delivery(
                    snapshot.delivery_id,
                    DeliveryTerminalReason.RUNTIME_FAILED,
                    lease_id=snapshot.lease_id,
                )
        except EventLedgerError as error:
            self.logger.warning("runtime {} completed invalid delivery {}: {}", record.spec.id, message.delivery_id, error)
            return
        self.logger.bind(
            runtime=record.spec.id,
            component="ipc",
            delivery_id=message.delivery_id,
            operation="event.completed",
            status=message.status,
            detail=message.detail,
        ).info("runtime event delivery {}", message.status)
        if self.delivery_completion_sink is not None:
            await self.delivery_completion_sink(record.spec.id, message)
        await self._schedule_ready_offers()

    async def _accept_child_event(self, record: RuntimeRecord, message: EventIngress) -> None:
        if record.protocol_version != 6:
            return
        if message.source_event_id in record.inbound_events:
            await self._send(
                record,
                EventAccepted(
                    delivery_id=message.source_event_id,
                    status="invalid",
                    detail="duplicate child source event id",
                ),
            )
            return
        if len(record.inbound_events) >= record.spec.max_inbound_events:
            await self._send(
                record,
                EventAccepted(
                    delivery_id=message.source_event_id,
                    status="overloaded",
                    detail="runtime inbound event capacity is exhausted",
                ),
            )
            return
        task = asyncio.create_task(
            self._execute_child_event(record, message),
            name=f"runtime-event:{record.spec.id}:{message.source_event_id}",
        )
        record.inbound_events[message.source_event_id] = task

    async def _execute_child_event(self, record: RuntimeRecord, message: EventIngress) -> None:
        detail: str | None = None
        try:
            status = "accepted" if self.event_sink is None else await self.event_sink(
                record.spec.id, message.source_event_id, message.payload
            )
            match status:
                case "accepted" | "overloaded" | "invalid":
                    normalized = status
                case _:
                    normalized = "invalid"
        except Exception as error:
            self.logger.error("runtime {} child event {} failed: {}", record.spec.id, message.source_event_id, error)
            normalized = "invalid"
            detail = "core event sink failed"
        try:
            await self._send(
                record,
                EventAccepted(
                    delivery_id=message.source_event_id,
                    status=normalized,
                    detail=detail,
                ),
            )
        except ConnectionError, RuntimeError:
            pass
        finally:
            record.inbound_events.pop(message.source_event_id, None)

    async def _accept_child_action(self, record: RuntimeRecord, request: ActionRequest) -> None:
        if record.protocol_version != 6:
            await self._reject_child_action(
                record,
                request,
                "child-originated actions require runtime protocol v6",
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
        try:
            delivery = self._find_delivery(request.delivery_id)
            if delivery.route.target_runtime_id != record.spec.id or delivery.lease_id is None:
                raise DeliveryTransitionError("action delivery is not owned by this runtime")
            claim = self.ledger.claim_action(
                delivery_id=delivery.delivery_id,
                lease_id=delivery.lease_id,
                correlation_id=request.correlation_id,
                payload=request.payload,
            )
        except EventLedgerError as error:
            await self._reject_child_action(record, request, str(error))
            return
        if claim.state is ActionClaimState.RECORDED:
            result = claim.record.result
            if isinstance(result, Mapping):
                await self._send(
                    record,
                    ActionResponse(
                        correlation_id=request.correlation_id,
                        ok=result.get("ok") is True,
                        data=result.get("data"),
                        error=result.get("error") if isinstance(result.get("error"), str) else None,
                    ),
                )
            return
        if claim.state is ActionClaimState.PENDING:
            await self._reject_child_action(record, request, "action request is already in progress")
            return
        event = self._event_for_delivery(delivery)
        provenance = ActionProvenance(
            delivery_id=delivery.delivery_id,
            source_runtime_id=delivery.provenance.source_runtime_id,
            source_event_id=delivery.provenance.source_event_id,
            event_payload=dict(event.payload),
        )
        if request.correlation_id in record.inbound_actions:
            await self._reject_child_action(
                record,
                request,
                f"duplicate action correlation id: {request.correlation_id}",
            )
            return

        task = asyncio.create_task(
            self._execute_child_action(record, request, provenance),
            name=f"runtime-action:{record.spec.id}:{request.correlation_id}",
        )
        record.inbound_actions[request.correlation_id] = task

    async def _execute_child_action(
        self,
        record: RuntimeRecord,
        request: ActionRequest,
        provenance: ActionProvenance,
    ) -> None:
        try:
            assert self.action_sink is not None
            self._log_payload(
                record,
                "action.child_request",
                request.correlation_id,
                request.payload,
            )
            result = await self.action_sink(record.spec.id, request.payload, provenance)
            delivery = self._find_delivery(request.delivery_id)
            assert delivery.lease_id is not None
            self.ledger.record_action_result(
                delivery_id=delivery.delivery_id,
                lease_id=delivery.lease_id,
                correlation_id=request.correlation_id,
                result={"ok": result.ok, "data": result.data, "error": result.error},
            )
            response = ActionResponse(
                correlation_id=request.correlation_id,
                ok=result.ok,
                data=result.data,
                error=result.error,
            )
        except Exception as error:
            try:
                delivery = self._find_delivery(request.delivery_id)
                if delivery.lease_id is not None:
                    self.ledger.record_action_result(
                        delivery_id=delivery.delivery_id,
                        lease_id=delivery.lease_id,
                        correlation_id=request.correlation_id,
                        result={"ok": False, "data": None, "error": "core action sink failed"},
                    )
            except EventLedgerError:
                pass
            self.logger.bind(delivery_id=provenance.delivery_id).error(
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
        if record.protocol_version != 6:
            await self._reject_agent_tool_request(
                record, request, "agent tools require runtime protocol v6"
            )
            return
        if record.spec.agent_harness is None:
            await self._reject_agent_tool_request(record, request, "runtime is not an agent harness")
            return
        if "agent.tools.execute" not in record.capabilities:
            await self._reject_agent_tool_request(record, request, "child runtime did not declare agent.tools.execute")
            return
        if self.agent_tool_sink is None:
            await self._reject_agent_tool_request(record, request, "agent tool broker is unavailable")
            return
        try:
            delivery = self._find_delivery(request.delivery_id)
            if delivery.route.target_runtime_id != record.spec.id or delivery.lease_id is None:
                raise DeliveryTransitionError("agent tool delivery is not owned by this runtime")
            claim = self.ledger.claim_action(
                delivery_id=delivery.delivery_id,
                lease_id=delivery.lease_id,
                correlation_id=request.correlation_id,
                payload={"agent_tool": request.tool_id, "arguments": request.arguments},
            )
        except EventLedgerError as error:
            await self._reject_agent_tool_request(
                record, request, str(error)
            )
            return
        if claim.state is ActionClaimState.RECORDED:
            result = claim.record.result
            if isinstance(result, Mapping):
                await self._send(
                    record,
                    AgentToolResponse(
                        correlation_id=request.correlation_id,
                        ok=result.get("ok") is True,
                        data=result.get("data"),
                        error=result.get("error") if isinstance(result.get("error"), str) else None,
                    ),
                )
            return
        if claim.state is ActionClaimState.PENDING:
            await self._reject_agent_tool_request(record, request, "agent tool request is already in progress")
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
            delivery = self._find_delivery(request.delivery_id)
            event = self._event_for_delivery(delivery)
            result = await self.agent_tool_sink(
                record.spec.id,
                request.delivery_id,
                dict(event.payload),
                request.tool_id,
                request.arguments,
            )
            assert delivery.lease_id is not None
            self.ledger.record_action_result(
                delivery_id=delivery.delivery_id,
                lease_id=delivery.lease_id,
                correlation_id=request.correlation_id,
                result={"ok": result.ok, "data": result.data, "error": result.error},
            )
            response = AgentToolResponse(
                correlation_id=request.correlation_id,
                ok=result.ok,
                data=result.data,
                error=result.error,
            )
        except Exception as error:
            try:
                delivery = self._find_delivery(request.delivery_id)
                if delivery.lease_id is not None:
                    self.ledger.record_action_result(
                        delivery_id=delivery.delivery_id,
                        lease_id=delivery.lease_id,
                        correlation_id=request.correlation_id,
                        result={"ok": False, "data": None, "error": "agent tool broker failed"},
                    )
            except EventLedgerError:
                pass
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

    async def _accept_management_request(self, record: RuntimeRecord, request: ManagementRequest) -> None:
        if record.protocol_version != 6 or "runtime.management.execute" not in record.capabilities:
            await self._reject_management_request(record, request, "runtime management is unavailable")
            return
        if self.management_sink is None:
            await self._reject_management_request(record, request, "kernel management is unavailable")
            return
        if request.correlation_id in record.inbound_management:
            await self._reject_management_request(record, request, "duplicate management correlation id")
            return
        task = asyncio.create_task(
            self._execute_management_request(record, request),
            name=f"runtime-management:{record.spec.id}:{request.correlation_id}",
        )
        record.inbound_management[request.correlation_id] = task

    async def _execute_management_request(self, record: RuntimeRecord, request: ManagementRequest) -> None:
        try:
            assert self.management_sink is not None
            ok, text, data, error = await self.management_sink(record.spec.id, request.command)
            response = ManagementResponse(
                correlation_id=request.correlation_id, ok=ok, text=text, data=data, error=error
            )
        except Exception:
            response = ManagementResponse(
                correlation_id=request.correlation_id,
                ok=False,
                error="kernel management failed",
            )
        try:
            await self._send(record, response)
        except (ConnectionError, RuntimeError):
            pass
        finally:
            record.inbound_management.pop(request.correlation_id, None)

    async def _reject_management_request(
        self, record: RuntimeRecord, request: ManagementRequest, error: str
    ) -> None:
        await self._send(record, ManagementResponse(correlation_id=request.correlation_id, ok=False, error=error))

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
                # Kernel-originated adapter actions are not child side effects and
                # intentionally bypass ledger lease validation at the receiving runtime.
                ActionRequest(
                    correlation_id=correlation_id,
                    delivery_id=f"kernel:{correlation_id}",
                    payload=json_mapping(payload),
                ),
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

    def admit_event(
        self,
        *,
        provenance: EventProvenance,
        payload: Mapping[str, Any],
        routes: Sequence[RouteSnapshot],
    ) -> str:
        event = self.ledger.admit(provenance=provenance, payload=payload, routes=routes)
        return event.event_id

    async def schedule_deliveries(self) -> None:
        """Offer one pending delivery per ledger ordering lane."""

        await self._schedule_ready_offers()

    async def wait_for_required(self, event_id: str) -> None:
        """Wait until all required deliveries are terminal, then surface failure."""

        while True:
            event = self.ledger.snapshot(event_id)
            if event.required_deliveries_terminal:
                if event.required_deliveries_succeeded is False:
                    raise RuntimeError(f"required runtime delivery failed for event {event_id}")
                return
            await asyncio.sleep(0.01)

    async def _schedule_ready_offers(self) -> None:
        for expired in self.ledger.expire():
            self.logger.warning("runtime delivery {} expired", expired.delivery_id)
        while offers := self.ledger.ready_offers(delivery_timeout_seconds=self._delivery_timeout_seconds):
            for delivery in offers:
                record = self.records.get(delivery.route.target_runtime_id)
                if record is None or record.state is not RuntimeState.READY or record.protocol_version != 6:
                    self.ledger.fail_delivery(delivery.delivery_id, DeliveryTerminalReason.DISCONNECTED)
                    continue
                if "runtime.events.receive" not in record.capabilities:
                    self.ledger.fail_delivery(delivery.delivery_id, DeliveryTerminalReason.RUNTIME_REJECTED)
                    continue
                try:
                    await self._send_delivery(record, delivery)
                except (ConnectionError, RuntimeError):
                    self.ledger.fail_delivery(delivery.delivery_id, DeliveryTerminalReason.SEND_FAILED)

    async def _send_delivery(self, record: RuntimeRecord, delivery: DeliverySnapshot) -> None:
        event = self._event_for_delivery(delivery)
        if delivery.lease_id is None or delivery.deadline is None:
            raise RuntimeError("ledger offered a delivery without a lease or deadline")
        message = EventMessage(
            kernel_event_id=event.event_id,
            source=EventSourceProvenance(
                source_runtime_id=delivery.provenance.source_runtime_id,
                source_event_id=delivery.provenance.source_event_id,
            ),
            delivery_id=delivery.delivery_id,
            target_runtime_id=record.spec.id,
            attempt=delivery.attempt,
            lease_id=delivery.lease_id,
            deadline_monotonic=delivery.deadline,
            payload=json_mapping(event.payload),
            agent_tool_catalog=(
                json_mapping(catalog)
                if self._agent_tool_catalog_provider is not None
                and (catalog := self._agent_tool_catalog_provider(delivery)) is not None
                else None
            ),
        )
        self._log_payload(record, "event.dispatch", delivery.delivery_id, message.payload)
        await self._send(record, message)

    def _find_delivery(self, delivery_id: str) -> DeliverySnapshot:
        for event in self.ledger.active_snapshots():
            for delivery in event.deliveries:
                if delivery.delivery_id == delivery_id:
                    return delivery
        raise DeliveryTransitionError(f"delivery {delivery_id!r} is not active")

    def _event_for_delivery(self, delivery: DeliverySnapshot):
        return self.ledger.snapshot(delivery.event_id)

    async def execute_control(
        self,
        runtime_id: str,
        correlation_id: str,
        command: Literal["agent.history.clear"],
        payload: Mapping[str, Any],
        timeout_seconds: float = 30.0,
    ) -> ControlResponse:
        if timeout_seconds <= 0:
            raise ValueError("runtime control timeout must be positive")
        record = self.records[runtime_id]
        if record.state is not RuntimeState.READY:
            raise RuntimeError(f"runtime {runtime_id} is not ready")
        if record.protocol_version != 6 or "runtime.controls.execute" not in record.capabilities:
            raise RuntimeError(f"runtime {runtime_id} does not accept protocol v6 controls")
        if correlation_id in record.pending_controls:
            raise ValueError(f"duplicate control correlation id: {correlation_id}")
        request = ControlRequest(
            correlation_id=correlation_id,
            command=command,
            payload=json_mapping(payload),
        )
        future: asyncio.Future[ControlResponse] = asyncio.get_running_loop().create_future()
        record.pending_controls[correlation_id] = future
        try:
            await self._send(record, request)
            async with asyncio.timeout(timeout_seconds):
                return await future
        finally:
            record.pending_controls.pop(correlation_id, None)

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

    async def start_runtime(self, runtime_id: str) -> None:
        """Start one configured runtime without restarting the supervisor."""

        if self._closing or not self._transport_started:
            raise RuntimeError("runtime supervisor is not running")
        record = self.records[runtime_id]
        if record.desired and record.runner is not None and not record.runner.done():
            if record.ready.is_set():
                return
            async with asyncio.timeout(record.spec.ready_timeout):
                await record.ready.wait()
            return
        if record.runner is not None and not record.runner.done():
            await self._request_stop(record, "start requested")
            await record.runner
        record.failures.clear()
        record.desired = True
        record.runner = asyncio.create_task(self._run(record), name=f"runtime:{runtime_id}")
        async with asyncio.timeout(record.spec.ready_timeout):
            await record.ready.wait()

    async def stop_runtime(self, runtime_id: str) -> None:
        """Stop one runtime while keeping the supervisor available to others."""

        record = self.records[runtime_id]
        await self._request_stop(record, "management stop")
        if record.runner is not None and record.runner is not asyncio.current_task():
            await record.runner

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
        self.ledger.shutdown()
        self._transport_started = False

    async def _request_stop(self, record: RuntimeRecord, reason: str) -> None:
        record.desired = False
        record.state = RuntimeState.STOPPING
        if record.identity is not None:
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
        router = record.router
        identity = record.identity
        lease_id = record.lease_id
        if router is None or identity is None or lease_id is None:
            raise ConnectionError(f"runtime {record.spec.id} is not connected")
        async with record.send_lock:
            lane = LyipLane.CONTROL if message.type in {
                "hello",
                "welcome",
                "config",
                "ready",
                "heartbeat",
                "shutdown",
                "control",
                "control_result",
                "management",
                "management_result",
                "error",
            } else LyipLane.BUSINESS
            sequence = record.send_sequences[lane]
            frame = encode_runtime_message(
                message,
                generation=record.generation,
                stream_id=self._outbound_stream_id(record, lane),
                sequence=sequence,
                lease_id=lease_id,
            )
            result = await router.offer(identity, frame)
            if result is LyipOfferResult.FULL:
                raise ConnectionError(f"runtime {record.spec.id} LYIP {lane.value} lane is full")
            record.send_sequences[lane] = sequence + 1

    async def _disconnect(self, record: RuntimeRecord) -> None:
        router, record.router = record.router, None
        record.identity = None
        record.expected_identity = None
        record.lease_id = None
        handshake_task, record.handshake_task = record.handshake_task, None
        receive_tasks, record.receive_tasks = record.receive_tasks, ()
        if handshake_task is not None and handshake_task is not asyncio.current_task():
            handshake_task.cancel()
        for task in receive_tasks:
            if task is not asyncio.current_task():
                task.cancel()
        transport_tasks = [
            task
            for task in (handshake_task, *receive_tasks)
            if task is not None and task is not asyncio.current_task()
        ]
        if transport_tasks:
            await asyncio.gather(*transport_tasks, return_exceptions=True)
        if router is not None:
            router.close()
        record.connected.clear()
        record.ready.clear()
        record.protocol_version = None
        record.capabilities = frozenset()
        for event in self.ledger.active_snapshots():
            for delivery in event.deliveries:
                if delivery.route.target_runtime_id == record.spec.id and not delivery.terminal:
                    self.ledger.fail_delivery(delivery.delivery_id, DeliveryTerminalReason.DISCONNECTED)
        for action_future in record.pending_actions.values():
            if not action_future.done():
                action_future.set_exception(ConnectionError(f"runtime {record.spec.id} disconnected"))
        record.pending_actions.clear()
        for control_future in record.pending_controls.values():
            if not control_future.done():
                control_future.set_exception(ConnectionError(f"runtime {record.spec.id} disconnected"))
        record.pending_controls.clear()
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
        inbound_management = tuple(record.inbound_management.values())
        record.inbound_management.clear()
        for task in inbound_management:
            task.cancel()
        if inbound_management:
            await asyncio.gather(*inbound_management, return_exceptions=True)
        if not self._closing:
            await self._schedule_ready_offers()

    async def _capture_output(
        self,
        record: RuntimeRecord,
        stream: asyncio.StreamReader,
        channel: Literal["stdout", "stderr"],
    ) -> None:
        logger = self.logger.bind(
            runtime=record.spec.id,
            component="runtime",
            stream=channel,
            upstream=record.spec.kind,
        )
        while line := await stream.readline():
            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if self.output_sink is not None:
                self.output_sink(record.spec.id, channel, text)
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
        if self._payload_mode(record) == "full":
            context["payload"] = serialized
        self.logger.bind(**context).debug("runtime IPC {}", operation)

    async def _watch_heartbeats(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            now = time.monotonic()
            for record in self.records.values():
                if record.state is RuntimeState.READY and now - record.last_heartbeat > record.spec.stale_after:
                    self.logger.error("runtime {} heartbeat timed out", record.spec.id)
                    if record.process is not None:
                        record.process.terminate()
            await self._schedule_ready_offers()
