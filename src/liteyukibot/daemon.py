"""One local daemon supervising one independently restartable kernel worker."""

from __future__ import annotations

import asyncio
import os
import secrets
import signal
from collections import deque
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from pathlib import Path
from time import monotonic
from typing import Any, cast

from .config import DaemonSettings, DevelopmentSettings, WebUISettings
from .control import ControlServer, request_control
from .instances import InstancePaths
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
        self.worker: asyncio.subprocess.Process | None = None
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
            "last_restart_reason": self._last_restart_reason,
            "webui": self._webui_status(),
        }

    async def run(self) -> int:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        await self.control.start()
        try:
            if self.webui.mode == "always":
                await self._start_webui()
            await self._start_worker()
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
            await self.operations.close()
            await self.control.stop()

    async def _start_worker(self) -> None:
        environment = {**os.environ, **self.worker_environment}
        environment["LITEYUKI_DAEMON_DESCRIPTOR"] = str(self.paths.daemon_descriptor)
        environment["LITEYUKI_DAEMON_WORKER"] = "1"
        self.worker = await asyncio.create_subprocess_exec(*self.worker_command, env=environment)
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

    async def _stop_webui(self) -> None:
        if self._webui_server is not None:
            await self._webui_server.stop()
            self._webui_server = None
        self._webui_tickets.clear()
        self._webui_subscribers.clear()

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
