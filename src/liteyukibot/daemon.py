"""One local daemon supervising one independently restartable kernel worker."""

from __future__ import annotations

import asyncio
import os
import secrets
import signal
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from time import monotonic
from typing import Any, cast

import zmq.asyncio

from .broker.lifecycle import BrokerLifecycleClient, BrokerLifecycleError
from .config import CONFIG_VERSION, DaemonSettings, DevelopmentSettings, WebUISettings
from .control import ControlServer, request_control
from .instances import InstancePaths
from .managed_graph import (
    ManagedGraphError,
    ManagedProcessGraph,
    ProcessLike,
    ProcessSpec,
    launch_process,
    terminate_process_tree,
)
from .operations import (
    ManagementPrincipal,
    OperationConfirmation,
    OperationDefinition,
    OperationImpact,
    OperationLedger,
    OperationRecord,
    OperationRequest,
    PrincipalKind,
)
from .profiles import ProfileError, ProfileStore
from .update import UpdateError, UpdateJournal, UpdatePhase


class InstanceDaemon:
    """Supervise a worker without owning the worker's data-directory lock."""

    def __init__(
        self,
        paths: InstancePaths,
        settings: DaemonSettings,
        worker_command: Sequence[str],
        worker_environment: Mapping[str, str],
        *,
        worker_descriptor: Path | None = None,
        development: DevelopmentSettings | None = None,
        webui: WebUISettings | None = None,
        watch_root: Path | None = None,
        validate_configuration: Callable[[], None] | None = None,
        broker_endpoint: str | None = None,
        broker_generation: int = 1,
        broker_diagnostics_token: str | None = None,
        broker_command: Sequence[str] | None = None,
        bridge_commands: Mapping[str, Sequence[str]] | None = None,
        broker_management_token: str | None = None,
        process_launcher: Callable[[ProcessSpec], Any] | None = None,
        orphan_process_terminator: Callable[[int], Awaitable[None]] | None = None,
    ) -> None:
        self.paths = paths
        self.settings = settings
        self.worker_command = tuple(worker_command)
        self.worker_environment = dict(worker_environment)
        self.worker_descriptor = worker_descriptor
        self.development = development or DevelopmentSettings()
        self.webui = webui or WebUISettings()
        self.watch_root = watch_root
        self.validate_configuration = validate_configuration
        self.profile_store = ProfileStore(paths.workspace)
        self.update_journal = UpdateJournal(paths.root / "update.json", instance=paths.name)
        self._update_lock = asyncio.Lock()
        self._broker_management_token = broker_management_token
        self._broker_lifecycle: BrokerLifecycleClient | None = None
        if broker_endpoint is not None and broker_management_token is not None:
            self._broker_lifecycle = BrokerLifecycleClient.from_broker_endpoint(
                context=zmq.asyncio.Context.instance(),
                endpoint=broker_endpoint,
                generation=broker_generation,
                identity=f"liteyuki-daemon:{paths.name}".encode(),
                management_token=broker_management_token,
            )
        self._broker_diagnostics = None
        if broker_endpoint is not None and broker_diagnostics_token is not None:
            from .broker import BrokerDiagnosticsClient

            self._broker_diagnostics = BrokerDiagnosticsClient.from_broker_endpoint(
                context=zmq.asyncio.Context.instance(),
                endpoint=broker_endpoint,
                generation=broker_generation,
                identity=f"liteyuki-webui:{paths.name}".encode(),
                diagnostics_token=broker_diagnostics_token,
            )
        self._broker_command = tuple(broker_command) if broker_command is not None else None
        self._bridge_commands = {bridge_id: tuple(command) for bridge_id, command in (bridge_commands or {}).items()}
        self._process_launcher = cast(Any, process_launcher or launch_process)
        self._orphan_process_terminator = orphan_process_terminator or terminate_process_tree
        self._graph = self._build_graph()
        self.worker: ProcessLike | None = None
        self._stop_event = asyncio.Event()
        self._restart_event = asyncio.Event()
        self._failures: deque[float] = deque()
        self._last_exit_code: int | None = None
        self._last_restart_reason: str | None = None
        self._watch_task: asyncio.Task[None] | None = None
        self._webui_server: Any = None
        self._webui_tickets: dict[str, float] = {}
        self._webui_events: deque[Any] = deque(maxlen=4096)
        self._webui_subscribers: set[asyncio.Queue[Any]] = set()
        self._broker_watch_task: asyncio.Task[None] | None = None
        self._webui_sequence = 0
        self._webui_operations_ready = False
        self.operations = OperationLedger(paths.root / "operations.sqlite3", audit_key=self._operation_audit_key())
        self._started_at = monotonic()
        self.control = ControlServer(
            paths.daemon_descriptor,
            status_provider=self.status,
            handlers={
                "stop": self._request_stop,
                "restart": self._request_restart,
                "webui.open": self._request_webui_open,
                "webui.status": self._request_webui_status,
                "update": self._request_update,
                "rollback": self._request_rollback,
            },
        )
        if self.development.enabled:
            self.control.handlers.update(
                {
                    "dev.status": self._worker_control,
                    "dev.topology": self._worker_control,
                    "dev.event.inject": self._worker_control,
                    "dev.management.execute": self._worker_control,
                }
            )

    def _build_graph(self, profile_python: Path | None = None) -> ManagedProcessGraph:
        base_environment = {**os.environ, **self.worker_environment}

        def command_for(command: Sequence[str]) -> tuple[str, ...]:
            if profile_python is None or not command:
                return tuple(command)
            return (str(profile_python), *tuple(command)[1:])

        specs: list[ProcessSpec] = []
        if self.settings.manage_broker and self._broker_command is not None:
            specs.append(ProcessSpec("broker", command_for(self._broker_command), base_environment))
        if self.settings.manage_bridges:
            specs.extend(
                ProcessSpec(f"bridge:{bridge_id}", command_for(command), base_environment)
                for bridge_id, command in sorted(self._bridge_commands.items())
            )
        worker_environment = {
            **base_environment,
            "LITEYUKI_DAEMON_DESCRIPTOR": str(self.paths.daemon_descriptor),
            "LITEYUKI_DAEMON_WORKER": "1",
        }
        specs.append(ProcessSpec("kernel", command_for(self.worker_command), worker_environment))
        return ManagedProcessGraph(
            specs,
            launcher=self._process_launcher,
            startup_timeout_seconds=self.settings.startup_timeout_seconds,
            stop_timeout_seconds=self.settings.stop_timeout_seconds,
        )

    def status(self) -> dict[str, object]:
        journal = self.update_journal.load()
        return {
            "schema_version": 2,
            "instance": self.paths.name,
            "state": "stopping" if self._stop_event.is_set() else "running",
            "uptime_seconds": max(0.0, monotonic() - self._started_at),
            "worker": {
                "pid": self.worker.pid if self.worker is not None else None,
                "returncode": self.worker.returncode if self.worker is not None else self._last_exit_code,
            },
            "failures_in_window": len(self._failures),
            "last_restart_reason": self._last_restart_reason,
            "managed_graph": self._graph.status(),
            "update": journal,
            "webui": self._webui_status(),
        }

    async def run(self) -> int:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        try:
            await self._recover_interrupted_update()
            if self.webui.mode == "always":
                await self._start_webui()
            await self._start_worker()
            await self.control.start()
            self._install_signal_handlers()
            if self.development.enabled and self.development.watch_auto_restart:
                self._watch_task = asyncio.create_task(self._watch_for_changes(), name="daemon-watch")
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
                self._last_restart_reason = f"worker exited with code {self._last_exit_code}"
                if self._last_exit_code == 0 or not self.settings.auto_restart or not self._can_restart():
                    return self._last_exit_code or 0
                await asyncio.sleep(self._restart_delay())
                await self._start_worker()
            return 0
        finally:
            if self._watch_task is not None:
                self._watch_task.cancel()
                await asyncio.gather(self._watch_task, return_exceptions=True)
            await self._terminate_worker()
            await self._stop_webui()
            if self._broker_lifecycle is not None:
                self._broker_lifecycle.close()
                self._broker_lifecycle = None
            await self.operations.close()
            await self.control.stop()

    async def _start_worker(self) -> None:
        await self._graph.start()
        self.worker = self._graph.processes.get("kernel")
        if self.worker is None:
            raise ManagedGraphError("managed graph did not start its kernel process")
        await self._publish_webui_event("reset", {"reason": "worker_started"})

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
        self.worker = None
        await self._graph.stop()

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

    def _operation_audit_key(self) -> bytes:
        path = self.paths.root / "operations.audit-key"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            key = path.read_bytes()
        except FileNotFoundError:
            key = secrets.token_bytes(32)
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                key = path.read_bytes()
            else:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(key)
                path.chmod(0o600)
        if len(key) != 32:
            raise RuntimeError("daemon operation audit key must contain exactly 32 bytes")
        return key

    async def _request_webui_open(self, _request: Mapping[str, Any]) -> dict[str, str]:
        if self.webui.mode == "disabled":
            raise PermissionError("WebUI is disabled by configuration")
        await self._start_webui()
        assert self._webui_server is not None
        return {"url": await self._webui_server.open()}

    async def _request_webui_status(self, _request: Mapping[str, Any]) -> dict[str, object]:
        return self._webui_status()

    def _webui_status(self) -> dict[str, object]:
        if self._webui_server is None:
            return {"state": "disabled" if self.webui.mode == "disabled" else "stopped", "mode": self.webui.mode}
        return {**self._webui_server.status(), "mode": self.webui.mode}

    async def _start_webui(self) -> None:
        if self._webui_server is not None:
            return
        try:
            from liteyukibot_webui import WebUiServer
        except ModuleNotFoundError as error:
            raise RuntimeError("WebUI support is not installed; install `liteyukibot-v7[webui]`") from error
        self._webui_server = WebUiServer(
            cast(Any, self),
            host="127.0.0.1",
            port=self.webui.port,
            session_idle_seconds=self.webui.session_idle_seconds,
            session_max_seconds=self.webui.session_max_seconds,
        )
        await self._webui_server.start()
        if self._broker_diagnostics is not None and self._broker_watch_task is None:
            self._broker_watch_task = asyncio.create_task(
                self._watch_broker_diagnostics(), name="webui-broker-diagnostics"
            )

    async def _stop_webui(self) -> None:
        if self._broker_watch_task is not None:
            self._broker_watch_task.cancel()
            await asyncio.gather(self._broker_watch_task, return_exceptions=True)
            self._broker_watch_task = None
        if self._webui_server is not None:
            await self._webui_server.stop()
            self._webui_server = None
        self._webui_tickets.clear()
        self._webui_subscribers.clear()
        if self._broker_diagnostics is not None:
            self._broker_diagnostics.close()
            self._broker_diagnostics = None

    async def issue_ticket(self) -> str:
        ticket = secrets.token_urlsafe(32)
        self._webui_tickets[ticket] = monotonic() + self.webui.ticket_ttl_seconds
        return ticket

    async def redeem_ticket(self, ticket: str) -> Any:
        expiry = self._webui_tickets.pop(ticket, None)
        if expiry is None or expiry < monotonic():
            return None
        from liteyukibot_webui import WebUiPrincipal

        return WebUiPrincipal(f"daemon:{self.paths.name}", frozenset({"liteyukibot.management.admin"}))

    async def authorize_session(self, principal: Any) -> bool:
        return (
            getattr(principal, "subject", None) == f"daemon:{self.paths.name}"
            and "liteyukibot.management.admin" in getattr(principal, "capabilities", ())
            and not self._stop_event.is_set()
        )

    async def bootstrap(self, _principal: Any) -> dict[str, object]:
        snapshot = await self._worker_webui_control("daemon.webui.snapshot")
        status = snapshot.get("status", {}) if isinstance(snapshot, Mapping) else {}
        runtime_health = status.get("runtime_health", {}) if isinstance(status, Mapping) else {}
        return {
            "instance": self.paths.name,
            "first_run": not runtime_health,
            "snapshot": snapshot,
            "webui": self._webui_status(),
        }

    async def presentation(self, _principal: Any, locale: str | None) -> dict[str, object]:
        request = {"locale": locale} if locale is not None else {}
        value = await self._worker_webui_control("daemon.webui.presentation", **request)
        return value if isinstance(value, dict) else {"locale": "en-US", "locales": [], "messages": {}}

    async def snapshot(self, _principal: Any) -> dict[str, object]:
        value = await self._worker_webui_control("daemon.webui.snapshot")
        return value if isinstance(value, dict) else {"state": "worker_unavailable"}

    async def operation_catalog(self, _principal: Any) -> dict[str, object]:
        await self._prepare_webui_operations()
        return {"operations": list(self.operations.catalog(self._webui_management_principal()))}

    async def submit_operation(self, _principal: Any, request: Mapping[str, Any]) -> dict[str, object]:
        await self._prepare_webui_operations()
        operation_id = request.get("operation_id")
        target = request.get("target")
        input_value = request.get("input")
        idempotency_key = request.get("idempotency_key")
        confirmation_target = request.get("confirmation_target")
        if (
            not isinstance(operation_id, str)
            or not isinstance(target, str)
            or not isinstance(input_value, Mapping)
            or not isinstance(idempotency_key, str)
            or confirmation_target is not None
            and not isinstance(confirmation_target, str)
        ):
            raise ValueError("invalid WebUI operation request")
        record = await self.operations.submit(
            self._webui_management_principal(),
            OperationRequest(
                operation=operation_id,
                target=target,
                input=input_value,
                idempotency_key=idempotency_key,
                confirmed=request.get("confirmed") is True,
                confirmation_target=confirmation_target,
            ),
        )
        await self._publish_webui_event("operation", self._operation_record(record))
        asyncio.create_task(self._publish_operation_completion(record.id), name=f"webui-operation:{record.id}")
        return self._operation_record(record)

    async def operation(self, _principal: Any, operation_id: str) -> dict[str, object] | None:
        record = self.operations.get(operation_id)
        return self._operation_record(record) if record is not None else None

    async def ledger(self, _principal: Any, cursor: str | None, limit: int) -> dict[str, object]:
        del cursor
        records = self.operations.records(limit)
        return {
            "items": [
                {
                    "id": record.id,
                    "at": record.updated_at.isoformat(),
                    "category": "operation",
                    "title": record.operation,
                    "source": record.target,
                    "status": self._ledger_status(record),
                    "trace": record.id,
                    "detail": record.result_code or record.state.value,
                }
                for record in records
            ],
            "next_cursor": None,
        }

    async def audit(self, _principal: Any, cursor: str | None, limit: int) -> dict[str, object]:
        del cursor
        return {
            "items": [self._operation_record(record) for record in self.operations.records(limit)],
            "next_cursor": None,
        }

    async def plugin_surfaces(self, _principal: Any) -> dict[str, object]:
        value = await self._worker_webui_control("daemon.webui.plugin_surfaces")
        return value if isinstance(value, dict) else {"generation": 0, "surfaces": [], "diagnostics": []}

    async def lyf_resources(self, _principal: Any) -> dict[str, object]:
        root = self.paths.workspace / "resources"
        if not root.is_dir():
            return {"read_only": True, "grammar": "source.lyf", "items": []}
        parse_function: Any = None
        try:
            from liteyukibot_functions import parse as parse_function
        except ModuleNotFoundError:
            pass
        items: list[dict[str, object]] = []
        for path in sorted(root.rglob("*.lyf")):
            if len(items) >= 100 or path.is_symlink() or not path.is_file():
                continue
            try:
                relative = path.resolve().relative_to(root.resolve()).as_posix()
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError, ValueError):
                continue
            if len(source.encode("utf-8")) > 256 * 1024:
                source = source[:256 * 1024]
            diagnostics: list[dict[str, object]] = []
            if parse_function is not None:
                diagnostics = [item.as_dict() for item in parse_function(source, source_id=relative).diagnostics]
            items.append({"path": relative, "source": source, "diagnostics": diagnostics})
        return {"read_only": True, "grammar": "source.lyf", "items": items}

    async def event_deliveries(
        self,
        _principal: Any,
        filters: Mapping[str, str],
        cursor: str | None,
        limit: int,
    ) -> dict[str, object]:
        if self._broker_diagnostics is None:
            return {
                "broker": {
                    "state": "disabled",
                    "active": 0,
                    "active_capacity": 0,
                    "terminal": 0,
                    "terminal_capacity": 0,
                    "bridges": [],
                },
                "items": [],
                "next_cursor": None,
            }
        try:
            status = await self._broker_diagnostics.status()
            page = await self._broker_diagnostics.list_events(cursor=cursor, limit=limit, **dict(filters))
        except Exception:
            return {
                "broker": {
                    "state": "unavailable",
                    "active": 0,
                    "active_capacity": 0,
                    "terminal": 0,
                    "terminal_capacity": 0,
                    "bridges": [],
                },
                "items": [],
                "next_cursor": None,
            }
        return {
            "broker": {
                "state": "ready",
                "generation": status.generation,
                "active": status.active_events,
                "active_capacity": status.active_capacity,
                "terminal": status.terminal_events,
                "terminal_capacity": status.terminal_capacity,
                "bridges": [
                    {"id": bridge_id, "state": "connected", "session_state": "registered"}
                    for bridge_id in status.sessions
                ],
            },
            "items": [
                {
                    "id": item.event_id,
                    "topic": item.topic,
                    "source": item.source_bridge_id,
                    "ordering_key": item.ordering_key,
                    "status": item.status,
                    "target_count": item.delivery_count,
                    "failed_count": item.failure_count,
                    "failure_code": item.failure_codes[0] if item.failure_codes else None,
                }
                for item in page.events
            ],
            "next_cursor": page.next_cursor,
        }

    async def event_delivery(self, _principal: Any, event_id: str) -> dict[str, object] | None:
        if self._broker_diagnostics is None:
            return None
        try:
            detail = await self._broker_diagnostics.detail(event_id)
        except Exception as error:
            if "unknown_event" in str(error) or "not retained" in str(error):
                return None
            raise
        return {
            "id": detail.event.event_id,
            "topic": detail.event.topic,
            "source": detail.event.source_bridge_id,
            "ordering_key": detail.event.ordering_key,
            "status": detail.event.status,
            "target_count": detail.event.delivery_count,
            "failed_count": detail.event.failure_count,
            "failure_code": detail.event.failure_codes[0] if detail.event.failure_codes else None,
            "deliveries": [
                {"target": target, "state": detail.event.status}
                for target in detail.event.targets
            ],
            "timeline": [
                {
                    "at": f"{item.elapsed_ms}ms",
                    "phase": item.kind,
                    "state": (
                        item.state
                        or ("succeeded" if item.success else "failed" if item.success is False else "observed")
                    ),
                    "target": item.target_bridge_id,
                    "code": item.failure_code,
                }
                for item in detail.transitions
            ],
        }

    async def replay_events(self, _principal: Any, after_id: str | None, limit: int) -> Any:
        from liteyukibot_webui import WebUiEventReplay

        events = tuple(self._webui_events)
        if after_id is None:
            return WebUiEventReplay(events[-limit:])
        for index, event in enumerate(events):
            if event.identifier == after_id:
                return WebUiEventReplay(events[index + 1 :][:limit])
        return WebUiEventReplay((), reset=bool(events))

    async def stream_events(self, _principal: Any, _after_id: str | None) -> AsyncIterator[Any]:
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=128)
        self._webui_subscribers.add(queue)
        try:
            while not self._stop_event.is_set():
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield self._new_webui_event("heartbeat", {"instance": self.paths.name})
        finally:
            self._webui_subscribers.discard(queue)

    async def _prepare_webui_operations(self) -> None:
        if self._webui_operations_ready:
            return
        value = await self._worker_webui_control("daemon.webui.operation_catalog")
        entries = value.get("operations", ()) if isinstance(value, Mapping) else ()
        if not isinstance(entries, list):
            raise RuntimeError("worker returned an invalid WebUI operation catalog")
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise RuntimeError("worker returned an invalid WebUI operation catalog entry")
            operation_id = entry.get("id")
            capability = entry.get("capability")
            schema = entry.get("input_schema")
            if not isinstance(operation_id, str) or not isinstance(capability, str) or not isinstance(schema, Mapping):
                raise RuntimeError("worker returned an invalid WebUI operation definition")
            api = entry.get("api")
            version = entry.get("version")
            target = entry.get("target")
            target_input_field = entry.get("target_input_field")
            mutating = entry.get("mutating") is True
            confirmation = OperationConfirmation(entry.get("confirmation", "none"))
            if mutating and confirmation is OperationConfirmation.NONE:
                raise RuntimeError("worker exposed an unconfirmed WebUI mutation")
            self.operations.register(
                OperationDefinition(
                    operation_id,
                    capability,
                    mutating=mutating,
                    cancellable=entry.get("cancellable") is True,
                    api=api if isinstance(api, str) else "liteyuki.management",
                    version=version if isinstance(version, int) else 1,
                    input_schema=schema,
                    impact=OperationImpact(entry.get("impact", "standard")),
                    confirmation=confirmation,
                    target=target if isinstance(target, str) else "kernel",
                    target_input_field=target_input_field if isinstance(target_input_field, str) else None,
                ),
                self._execute_worker_operation,
            )
        await self.operations.start()
        self._webui_operations_ready = True

    async def _watch_broker_diagnostics(self) -> None:
        assert self._broker_diagnostics is not None
        previous: tuple[int, int, int] | None = None
        while not self._stop_event.is_set():
            try:
                status = await self._broker_diagnostics.status()
                current = (status.active_events, status.terminal_events, status.generation)
                if previous is not None and current != previous:
                    await self._publish_webui_event("event_delivery", {"reason": "broker_changed"})
                previous = current
            except Exception:
                previous = None
            await asyncio.sleep(2)

    async def _execute_worker_operation(self, _principal: ManagementPrincipal, request: OperationRequest) -> str:
        value = await self._worker_webui_control(
            "daemon.webui.operation.execute",
            operation_id=request.operation,
            target=request.target,
            input=dict(request.input),
            idempotency_key=request.idempotency_key,
            confirmed=request.confirmed,
            confirmation_target=request.confirmation_target,
        )
        if not isinstance(value, Mapping) or not isinstance(value.get("result_code"), str):
            raise RuntimeError("worker returned an invalid WebUI operation result")
        return cast(str, value["result_code"])

    async def _worker_webui_control(self, command: str, **parameters: object) -> Any:
        if self.worker_descriptor is None:
            raise RuntimeError("WebUI worker bridge is unavailable")
        return await cast(Any, request_control)(self.worker_descriptor, command, **parameters)

    def _webui_management_principal(self) -> ManagementPrincipal:
        return ManagementPrincipal(
            PrincipalKind.WEB_SESSION,
            f"daemon:{self.paths.name}",
            "loopback-webui",
            None,
            frozenset({"liteyukibot.management.admin"}),
        )

    @staticmethod
    def _operation_record(record: OperationRecord) -> dict[str, object]:
        return {
            "id": record.id,
            "operation": record.operation,
            "target": record.target,
            "state": record.state.value,
            "result_code": record.result_code,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    @staticmethod
    def _ledger_status(record: OperationRecord) -> str:
        if record.state.value == "succeeded":
            return "healthy"
        if record.state.value in {"failed", "unknown"}:
            return "critical"
        return "attention"

    async def _publish_operation_completion(self, operation_id: str) -> None:
        while not self._stop_event.is_set():
            record = self.operations.get(operation_id)
            if record is None:
                return
            if record.state.value not in {"queued", "running"}:
                await self._publish_webui_event("operation", self._operation_record(record))
                return
            await asyncio.sleep(0.02)

    def _new_webui_event(self, event: str, data: Mapping[str, object]) -> Any:
        from liteyukibot_webui import WebUiEvent

        self._webui_sequence += 1
        return WebUiEvent(event, cast(Any, data), str(self._webui_sequence))

    async def _publish_webui_event(self, event: str, data: Mapping[str, object]) -> None:
        item = self._new_webui_event(event, data)
        self._webui_events.append(item)
        for queue in tuple(self._webui_subscribers):
            if queue.full():
                continue
            queue.put_nowait(item)

    async def _recover_interrupted_update(self) -> None:
        journal = self.update_journal.load()
        if journal is None or self.update_journal.is_terminal(journal):
            return
        stopped, failures = await self._stop_journaled_processes(journal)
        previous = journal.get("previous_profile")
        previous_python: Path | None = None
        if isinstance(previous, str) and self.profile_store.active() != previous:
            self.profile_store.activate(previous)
        if isinstance(previous, str):
            previous_python = ProfileStore.python_path(self.profile_store.profile_path(previous)).resolve()
            self._graph = self._build_graph(previous_python)
        reason = f"daemon restarted during a non-terminal update; stopped {len(stopped)} recorded process(es)"
        if failures:
            reason += "; failed to stop " + ", ".join(failures)
        self.update_journal.recover(reason=reason)

    async def _stop_journaled_processes(
        self, journal: Mapping[str, object]
    ) -> tuple[tuple[tuple[str, int], ...], tuple[str, ...]]:
        stopped: list[tuple[str, int]] = []
        failures: list[str] = []
        for name, pid in self._journal_graph_processes(journal):
            if pid == os.getpid():
                continue
            try:
                await self._orphan_process_terminator(pid)
            except Exception as error:
                failures.append(f"{name}({pid}): {error}")
            else:
                stopped.append((name, pid))
        return tuple(stopped), tuple(failures)

    @staticmethod
    def _journal_graph_processes(journal: Mapping[str, object]) -> tuple[tuple[str, int], ...]:
        history = journal.get("history")
        if not isinstance(history, list):
            return ()
        graphs: dict[str, Mapping[str, object]] = {}
        for item in history:
            if not isinstance(item, Mapping):
                continue
            phase = item.get("phase")
            detail = item.get("detail")
            if not isinstance(detail, Mapping):
                continue
            role = detail.get("role")
            graph = detail.get("graph")
            if (
                not isinstance(role, str)
                or role not in {"candidate", "previous"}
                or not isinstance(graph, Mapping)
            ):
                if phase in {UpdatePhase.STARTING.value, UpdatePhase.HEALTHY.value} and "processes" in detail:
                    role = "candidate"
                    graph = detail
                else:
                    continue
            graphs[role] = graph

        processes_to_stop: list[tuple[str, int]] = []
        seen_pids: set[int] = set()
        for role in ("candidate", "previous"):
            graph = graphs.get(role)
            if graph is None:
                continue
            process_map = graph.get("processes")
            if not isinstance(process_map, Mapping):
                continue
            stop_order = graph.get("stop_order")
            names = [name for name in stop_order if isinstance(name, str)] if isinstance(stop_order, list) else []
            names.extend(name for name in process_map if isinstance(name, str) and name not in names)
            for name in names:
                record = process_map.get(name)
                if not isinstance(record, Mapping):
                    continue
                pid = record.get("pid")
                if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 or pid in seen_pids:
                    continue
                seen_pids.add(pid)
                processes_to_stop.append((name, pid))
        return tuple(processes_to_stop)

    async def _request_update(self, request: Mapping[str, Any]) -> dict[str, object]:
        profile_id = request.get("profile_id")
        if not isinstance(profile_id, str) or not profile_id:
            raise ValueError("update requires a staged profile_id")
        return await self._update_profile(profile_id)

    async def _request_rollback(self, _request: Mapping[str, Any]) -> dict[str, object]:
        async with self._update_lock:
            profile_id = self.profile_store.previous()
        return await self._update_profile(profile_id)

    async def _update_profile(self, profile_id: str) -> dict[str, object]:
        if not self._graph.managed:
            raise UpdateError("instance is not eligible for atomic updates; daemon must own Broker and Kernel")
        if self._broker_lifecycle is None:
            raise UpdateError("atomic updates require broker management token configuration")
        async with self._update_lock:
            active = self.profile_store.active()
            if active is None:
                raise ProfileError("atomic updates require an active verified profile")
            if profile_id == active:
                raise ProfileError("update candidate is already the active profile")
            candidate = self.profile_store.read_manifest(profile_id)
            if candidate.config_version != CONFIG_VERSION:
                raise UpdateError(
                    f"migration_required: candidate profile requires config v{candidate.config_version}; "
                    f"active daemon contract is v{CONFIG_VERSION}"
                )
            if candidate.bundle_tag != "v7.0.0a9" or candidate.bundle_version != "7.0.0a9":
                raise UpdateError("candidate profile is not an Alpha9 verified bundle")
            self.update_journal.begin(candidate_profile=profile_id, previous_profile=active)
            admission_frozen = False
            kernel_frozen = False
            profile_switched = False
            try:
                self.update_journal.transition(
                    UpdatePhase.STAGED,
                    detail={"profile_id": profile_id, "role": "previous", "graph": self._graph.status()},
                )
                broker_status = await self._broker_lifecycle.freeze("instance update")
                admission_frozen = broker_status.frozen
                self.update_journal.transition(
                    UpdatePhase.ADMISSION_FROZEN,
                    detail={"active_events": broker_status.active_events},
                )
                await self._drain_broker()
                self.update_journal.transition(UpdatePhase.DRAINED)
                await self._freeze_kernel()
                kernel_frozen = True
                self.update_journal.transition(
                    UpdatePhase.KERNEL_FROZEN,
                    detail={"role": "previous", "graph": self._graph.status()},
                )
                await self._terminate_worker()
                self.update_journal.transition(UpdatePhase.STOPPED)
                self.profile_store.activate(profile_id)
                profile_switched = True
                self.update_journal.transition(UpdatePhase.PROFILE_SWITCHED, detail={"profile_id": profile_id})
                candidate_python = ProfileStore.python_path(self.profile_store.profile_path(profile_id)).resolve()
                self._graph = self._build_graph(candidate_python)
                self.update_journal.transition(
                    UpdatePhase.STARTING,
                    detail={"role": "candidate", "graph": self._graph.status()},
                )
                await self._start_worker()
                self.update_journal.transition(
                    UpdatePhase.STARTING,
                    detail={"role": "candidate", "graph": self._graph.status()},
                )
                await self._wait_kernel_healthy()
                self.update_journal.transition(
                    UpdatePhase.HEALTHY,
                    detail={"role": "candidate", "graph": self._graph.status()},
                )
                self.update_journal.transition(UpdatePhase.COMMITTED)
                return {"accepted": True, "profile_id": profile_id, "phase": UpdatePhase.COMMITTED.value}
            except BaseException as error:
                await self._recover_failed_update(
                    active=active,
                    profile_switched=profile_switched,
                    admission_frozen=admission_frozen,
                    kernel_frozen=kernel_frozen,
                    error=error,
                )
                raise

    async def _drain_broker(self) -> None:
        deadline = monotonic() + self.settings.drain_timeout_seconds
        while True:
            assert self._broker_lifecycle is not None
            status = await self._broker_lifecycle.drain()
            if status.active_events == 0:
                return
            if monotonic() >= deadline:
                await self._broker_lifecycle.unfreeze()
                raise UpdateError("broker drain timed out; admission was restored")
            await asyncio.sleep(0.05)

    async def _freeze_kernel(self) -> None:
        if self.worker_descriptor is None:
            raise UpdateError("managed update requires the Kernel control descriptor")
        value = await request_control(self.worker_descriptor, "daemon.lifecycle.freeze")
        if not isinstance(value, Mapping) or value.get("frozen") is not True:
            raise UpdateError("Kernel did not acknowledge lifecycle freeze")

    async def _wait_kernel_healthy(self) -> None:
        if self.worker_descriptor is None:
            return
        deadline = monotonic() + self.settings.health_timeout_seconds
        while True:
            try:
                value = await request_control(self.worker_descriptor, "status")
            except Exception as error:
                if monotonic() >= deadline:
                    raise UpdateError("candidate Kernel did not become healthy") from error
            else:
                if isinstance(value, Mapping) and value.get("state") == "ready":
                    return
                if monotonic() >= deadline:
                    raise UpdateError("candidate Kernel reported an unhealthy state")
            await asyncio.sleep(0.05)

    async def _recover_failed_update(
        self,
        *,
        active: str,
        profile_switched: bool,
        admission_frozen: bool,
        kernel_frozen: bool,
        error: BaseException,
    ) -> None:
        detail = str(error)
        if not kernel_frozen and not profile_switched:
            if admission_frozen and self._broker_lifecycle is not None:
                try:
                    await self._broker_lifecycle.unfreeze()
                except BrokerLifecycleError:
                    pass
            try:
                self.update_journal.transition(UpdatePhase.ABORTED, error=detail)
            except UpdateError:
                pass
            return
        try:
            if self.update_journal.load() is not None:
                self.update_journal.transition(UpdatePhase.ROLLING_BACK, error=detail)
        except UpdateError:
            pass
        if kernel_frozen and self.worker_descriptor is not None and self.worker is not None:
            try:
                await request_control(self.worker_descriptor, "daemon.lifecycle.unfreeze")
            except Exception:
                pass
        if profile_switched or self._graph.processes:
            await self._terminate_worker()
        if profile_switched:
            self.profile_store.activate(active)
        self._graph = self._build_graph(
            ProfileStore.python_path(self.profile_store.profile_path(active)).resolve()
            if self.profile_store.active() == active
            else None
        )
        try:
            await self._start_worker()
            await self._wait_kernel_healthy()
        except BaseException as restart_error:
            detail = f"{detail}; previous graph restart failed: {restart_error}"
        if admission_frozen and self._broker_lifecycle is not None and self._graph.processes:
            try:
                await self._broker_lifecycle.unfreeze()
            except BrokerLifecycleError:
                pass
        try:
            self.update_journal.transition(UpdatePhase.ROLLED_BACK, error=detail)
        except UpdateError:
            pass

    async def _request_stop(self, _request: Mapping[str, Any]) -> dict[str, object]:
        self._stop_event.set()
        return {"accepted": True}

    async def _request_restart(self, _request: Mapping[str, Any]) -> dict[str, object]:
        reason = _request.get("reason", "explicit CLI restart")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("restart reason must be a non-empty string")
        self._last_restart_reason = reason.strip()
        self._restart_event.set()
        return {"accepted": True}

    async def _worker_control(self, request: Mapping[str, Any]) -> Any:
        if not self.development.enabled or self.worker_descriptor is None:
            raise PermissionError("development controls are disabled")
        command = request.get("command")
        if not isinstance(command, str) or not command.startswith("dev."):
            raise ValueError("invalid development control command")
        forwarded = command.removeprefix("dev.")
        parameters = {key: value for key, value in request.items() if key not in {"command", "token"}}
        return await request_control(self.worker_descriptor, forwarded, **parameters)

    async def _watch_for_changes(self) -> None:
        if self.watch_root is None or self.validate_configuration is None:
            return
        snapshot = self._watch_snapshot()
        changed_at: float | None = None
        while not self._stop_event.is_set():
            await asyncio.sleep(0.25)
            current = self._watch_snapshot()
            if current != snapshot:
                snapshot = current
                changed_at = monotonic()
            if changed_at is None or monotonic() - changed_at < self.development.watch_debounce_seconds:
                continue
            changed_at = None
            try:
                self.validate_configuration()
            except Exception:
                continue
            self._last_restart_reason = "development file change"
            self._restart_event.set()

    def _watch_snapshot(self) -> dict[Path, tuple[int, int]]:
        if self.watch_root is None or not self.watch_root.is_dir():
            return {}
        ignored = {".git", ".venv", "dist", "data", "cache"}
        snapshot: dict[Path, tuple[int, int]] = {}
        instance_overlay = Path(".liteyuki") / "instances" / f"{self.paths.name}.toml"
        for path in self.watch_root.rglob("*"):
            relative = path.relative_to(self.watch_root)
            if not path.is_file() or any(part in ignored for part in relative.parts):
                continue
            if relative.parts and relative.parts[0] == ".liteyuki" and relative != instance_overlay:
                continue
            if relative.parts and relative.parts[0] == "resources":
                pass
            elif path.suffix not in {".py", ".toml", ".json", ".yaml", ".yml"}:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            snapshot[path] = (stat.st_mtime_ns, stat.st_size)
        return snapshot

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
