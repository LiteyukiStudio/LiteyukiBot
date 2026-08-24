"""One local daemon supervising one independently restartable kernel worker."""

from __future__ import annotations

import asyncio
import os
import secrets
import signal
import tomllib
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from time import monotonic
from typing import Any, cast

import zmq.asyncio

from .broker.lifecycle import BrokerLifecycleClient, BrokerLifecycleError
from .broker.service import BridgeCatalog
from .config import CONFIG_VERSION, DaemonSettings, DevelopmentSettings, WebUISettings
from .config.documents import read_document, write_document
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
from .plugin_install import PluginInstallationService
from .plugin_sources import OFFICIAL_SOURCE_ID, PluginSourceStore
from .plugin_store import (
    PLUGIN_GENERATION_ENV,
    PlatformTarget,
    PluginBundle,
    PluginIndex,
    PluginStoreError,
    RuntimeGeneration,
    RuntimeGenerationStore,
)
from .profiles import ProfileError, ProfileStore
from .runtime import RuntimeCatalog
from .update import UpdateError, UpdateJournal, UpdatePhase

_MAX_PLUGIN_QUERY_LENGTH = 128
_MAX_PLUGIN_RESULTS = 10_000
_MAX_PLUGIN_PAGE_SIZE = 100
_MAX_PLUGIN_CLOSURE = 128


def _plugin_source_document(source: Any, digest: str | None) -> dict[str, object]:
    """Project source identity without exposing workspace cache paths.

    Args:
        source: Input accepted by this callable.
        digest: Input accepted by this callable.

    Returns:
        Result produced by this callable.

    Notes:
        This helper remains internal to its owning implementation.
    """
    return {
        "id": source.id,
        "priority": source.priority,
        "official": source.id == OFFICIAL_SOURCE_ID,
        "url": source.url,
        "cache_state": "cached" if digest is not None else "uncached",
        "digest": digest,
    }


def _plugin_bundle_document(bundle: PluginBundle) -> dict[str, object]:
    """Project publisher-controlled bundle metadata as JSON-safe text and counts.

    Args:
        bundle: Input accepted by this callable.

    Returns:
        Result produced by this callable.

    Notes:
        This helper remains internal to its owning implementation.
    """
    inputs = tuple(artifact for facet in bundle.facets for artifact in (*facet.artifacts, *facet.wheels))
    known_bytes = tuple(artifact.bytes for artifact in inputs)
    exact_bytes = tuple(value for value in known_bytes if value is not None)
    publisher = bundle.publisher
    license_value = bundle.license
    return {
        "bundle_id": bundle.id,
        "version": bundle.version,
        "display_name": bundle.display_name or bundle.id,
        "summary": bundle.summary or "",
        "publisher": publisher.document() if publisher is not None else None,
        "license": license_value.document() if license_value is not None else None,
        "status": bundle.status,
        "yanked_reason": bundle.yanked_reason,
        "runtime_kinds": sorted({facet.runtime_kind for facet in bundle.facets}),
        "requested_capabilities": sorted({capability for facet in bundle.facets for capability in facet.capabilities}),
        "dependencies": list(bundle.dependencies),
        "repository": bundle.repository,
        "homepage": bundle.homepage,
        "project_id": bundle.project_id or bundle.id,
        "description": bundle.description or bundle.summary or "",
        "tags": list(bundle.tags),
        "compatibility": list(bundle.compatibility),
        "gallery": list(bundle.gallery),
        "changelog": list(bundle.changelog),
        "download_bytes": sum(exact_bytes) if len(exact_bytes) == len(known_bytes) else None,
        "download_bytes_exact": all(value is not None for value in known_bytes),
    }


def _resolve_plugin_closure(index: PluginIndex, root: str) -> tuple[PluginBundle, ...]:
    """Resolve one bounded dependency closure in installation order.

    Args:
        index: Input accepted by this callable.
        root: Input accepted by this callable.

    Returns:
        Result produced by this callable.

    Notes:
        This helper remains internal to its owning implementation.
    """
    visiting: set[str] = set()
    visited: set[str] = set()
    resolved: list[PluginBundle] = []

    def visit(bundle_id: str) -> None:
        """Handle `_resolve_plugin_closure.visit`.

        Args:
            bundle_id: Input accepted by this callable.

        Returns:
            Result produced by this callable.
        """
        if bundle_id in visited:
            return
        if bundle_id in visiting:
            raise PluginStoreError("plugin dependency cycle")
        if len(visited) >= _MAX_PLUGIN_CLOSURE:
            raise PluginStoreError("plugin dependency closure exceeds the WebUI limit")
        visiting.add(bundle_id)
        bundle = index.require(bundle_id)
        for dependency in bundle.dependencies:
            visit(dependency)
        visiting.remove(bundle_id)
        visited.add(bundle_id)
        resolved.append(bundle)

    visit(root)
    return tuple(resolved)


def _plugin_generation_document(generation: RuntimeGeneration | None) -> dict[str, object] | None:
    """Project generation identity while excluding load plans and artifact paths.

    Args:
        generation: Input accepted by this callable.

    Returns:
        Result produced by this callable.

    Notes:
        This helper remains internal to its owning implementation.
    """
    if generation is None:
        return None
    enabled = tuple(root for root in generation.roots if root not in generation.disabled_roots)
    return {
        "id": generation.id,
        "runtime_id": generation.runtime_id,
        "runtime_kind": generation.runtime_kind,
        "created_at": generation.created_at,
        "bundles": list(generation.bundles),
        "roots": list(generation.roots),
        "disabled_roots": list(generation.disabled_roots),
        "enabled_bundle_set": list(enabled),
        "source_id": generation.source_id,
        "index_digest": generation.index_digest,
    }


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
        bridge_kinds: Mapping[str, str] | None = None,
        broker_management_token: str | None = None,
        process_launcher: Callable[[ProcessSpec], Any] | None = None,
        orphan_process_terminator: Callable[[int], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the instance daemon.

        Args:
            paths: The paths value used by the operation.
            settings: Validated application settings.
            worker_command: The worker command value used by the operation.
            worker_environment: The worker environment value used by the operation.
            worker_descriptor: The worker descriptor value used by the operation.
            development: The development value used by the operation.
            webui: The webui value used by the operation.
            watch_root: The watch root value used by the operation.
            validate_configuration: The validate configuration value used by the operation.
            broker_endpoint: The broker endpoint value used by the operation.
            broker_generation: The broker generation value used by the operation.
            broker_diagnostics_token: The broker diagnostics token value used by the operation.
            broker_command: The broker command value used by the operation.
            bridge_commands: The bridge commands value used by the operation.
            bridge_kinds: Configured runtime kind for each managed bridge ID.
            broker_management_token: The broker management token value used by the operation.
            process_launcher: The process launcher value used by the operation.
            orphan_process_terminator: The orphan process terminator value used by the operation.

        Returns:
            None.
        """
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
        self._bridge_kinds = dict(bridge_kinds or {})
        if not set(self._bridge_kinds).issubset(self._bridge_commands):
            raise ValueError("managed bridge kinds must refer to configured bridge commands")
        self._process_launcher = cast(Any, process_launcher or launch_process)
        self._orphan_process_terminator = orphan_process_terminator or terminate_process_tree
        self._graph = self._build_graph()
        self.worker: ProcessLike | None = None
        self._stop_event = asyncio.Event()
        self._restart_event = asyncio.Event()
        self._failures: deque[float] = deque()
        self._last_exit_code: int | None = None
        self._last_restart_reason: str | None = None
        self._restart_plugin_target: str | None = None
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
                "resources.reload": self._request_resources_reload,
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
        """Build graph.

        Args:
            profile_python: The profile python value used by the operation.

        Returns:
            The `ManagedProcessGraph` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._build_graph`. It delegates to `append`,
            `command_for`, `extend`, `sorted` while keeping intermediate state local to the owning
            operation.
        """
        base_environment = {**os.environ, **self.worker_environment}
        generations = RuntimeGenerationStore(self.paths.workspace)
        deployment = generations.active()

        def command_for(command: Sequence[str]) -> tuple[str, ...]:
            """Implement the command for operation for the build graph.

            Args:
                command: Command or operation name to execute.

            Returns:
                The `tuple[str, ...]` result produced by the operation.

            Notes:
                Internal implementation detail for `InstanceDaemon._build_graph.command_for`. It performs the
                local state transition directly and is not a stable extension boundary.
            """
            if profile_python is None or not command:
                return tuple(command)
            return (str(profile_python), *tuple(command)[1:])

        specs: list[ProcessSpec] = []
        if self.settings.manage_broker and self._broker_command is not None:
            specs.append(ProcessSpec("broker", command_for(self._broker_command), base_environment))
        if self.settings.manage_bridges:
            for bridge_id, command in sorted(self._bridge_commands.items()):
                bridge_environment = dict(base_environment)
                generation_id = deployment.runtime_generations.get(bridge_id)
                if generation_id is None:
                    bridge_command = command_for(command)
                else:
                    generation = generations.read(bridge_id, generation_id)
                    configured_kind = self._bridge_kinds.get(bridge_id)
                    if configured_kind is None:
                        raise ManagedGraphError(f"bridge {bridge_id!r} has a generation but no configured kind")
                    if generation.runtime_kind != configured_kind:
                        raise ManagedGraphError(
                            f"bridge {bridge_id!r} generation kind {generation.runtime_kind!r} does not match "
                            f"configured kind {configured_kind!r}"
                        )
                    generation_path = generations.path_for(bridge_id, generation_id)
                    generation_python = generations.python_path(generation_path)
                    if not generation_python.is_file():
                        raise ManagedGraphError(f"bridge {bridge_id!r} generation Python is unavailable")
                    bridge_command = (str(generation_python), *tuple(command)[1:])
                    bridge_environment[PLUGIN_GENERATION_ENV] = str(generation_path)
                specs.append(ProcessSpec(f"bridge:{bridge_id}", bridge_command, bridge_environment))
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
        """Return the status of the instance daemon operation.

        Returns:
            The requested `dict[str, object]` value.
        """
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
        """Run the instance daemon until its lifecycle completes.

        Returns:
            The `int` result produced by the operation.
        """
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
                    await self._restart_worker_graph()
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
        """Start worker.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._start_worker`. It delegates to `start`,
            `get`, `_publish_webui_event` while keeping intermediate state local to the owning operation.
        """
        await self._graph.start()
        self.worker = self._graph.processes.get("kernel")
        if self.worker is None:
            raise ManagedGraphError("managed graph did not start its kernel process")
        await self._publish_webui_event("reset", {"reason": "worker_started"})

    async def _restart_worker_graph(self) -> None:
        """Rebuild the graph and roll back a failed plugin generation candidate.

        Returns:
            None.

        Notes:
            The prior graph is retained until the candidate graph starts. Only
            plugin-target restarts mutate deployment state on failure; ordinary
            restart failures continue to propagate.

        Security:
            A plugin lifecycle restart may introduce arbitrary bridge-process
            code. The prior process graph and deployment pointer are retained
            until the candidate survives managed startup readiness. This is a
            rollback boundary, not a sandbox for hostile plugins.
        """
        previous_graph = self._graph
        kernel_spec = next(spec for spec in previous_graph.specs if spec.name == "kernel")
        profile_python = Path(kernel_spec.command[0])
        plugin_target = self._restart_plugin_target
        await self._terminate_worker()
        try:
            self._graph = self._build_graph(profile_python)
            await self._start_worker()
        except Exception as error:
            if plugin_target is None:
                raise
            generations = RuntimeGenerationStore(self.paths.workspace)
            try:
                generations.rollback(plugin_target)
            except PluginStoreError:
                generations.deactivate(plugin_target)
            self._graph = previous_graph
            await self._start_worker()
            self._last_restart_reason = f"plugin target {plugin_target!r} failed startup and was rolled back: {error}"
        finally:
            self._failures.clear()
            self._restart_event.clear()
            self._restart_plugin_target = None

    async def _wait_for_worker_change(self) -> str:
        """Wait for for worker change.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._wait_for_worker_change`. It delegates to
            `create_task`, `wait`, `cancel`, `gather` while keeping intermediate state local to the owning
            operation.
        """
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
        """Implement the terminate worker operation for the instance daemon.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._terminate_worker`. It delegates to `stop`
            while keeping intermediate state local to the owning operation.
        """
        self.worker = None
        await self._graph.stop()

    def _can_restart(self) -> bool:
        """Implement the can restart operation for the instance daemon.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `InstanceDaemon._can_restart`. It delegates to `monotonic`,
            `popleft`, `append` while keeping intermediate state local to the owning operation.
        """
        now = monotonic()
        while self._failures and now - self._failures[0] > self.settings.restart_window_seconds:
            self._failures.popleft()
        self._failures.append(now)
        return len(self._failures) <= self.settings.restart_limit

    def _restart_delay(self) -> float:
        """Implement the restart delay operation for the instance daemon.

        Returns:
            The `float` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._restart_delay`. It delegates to `max`,
            `min`, `float` while keeping intermediate state local to the owning operation.
        """
        exponent = max(0, len(self._failures) - 1)
        delay = min(
            self.settings.restart_backoff_max_seconds,
            self.settings.restart_backoff_initial_seconds * (2**exponent),
        )
        return float(delay)

    def _operation_audit_key(self) -> bytes:
        """Implement the operation audit key operation for the instance daemon.

        Returns:
            The `bytes` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._operation_audit_key`. It delegates to
            `mkdir`, `read_bytes`, `token_bytes`, `open` while keeping intermediate state local to the
            owning operation.
        """
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
        """Request webui open.

        Args:
            _request: The request value used by the operation.

        Returns:
            The `dict[str, str]` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._request_webui_open`. It delegates to
            `_start_webui`, `open` while keeping intermediate state local to the owning operation.
        """
        if self.webui.mode == "disabled":
            raise PermissionError("WebUI is disabled by configuration")
        await self._start_webui()
        assert self._webui_server is not None
        return {"url": await self._webui_server.open()}

    async def _request_resources_reload(self, _request: Mapping[str, Any]) -> dict[str, object]:
        """Reload kernel resource packs without restarting the daemon.

        Args:
            _request: Input accepted by this callable.

        Returns:
            Result produced by this callable.

        Notes:
            This helper remains internal to its owning implementation.
        """
        value = await self._worker_webui_control("daemon.resources.reload")
        return value if isinstance(value, dict) else {"packs": []}

    async def _request_webui_status(self, _request: Mapping[str, Any]) -> dict[str, object]:
        """Request webui status.

        Args:
            _request: The request value used by the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._request_webui_status`. It delegates to
            `_webui_status` while keeping intermediate state local to the owning operation.
        """
        return self._webui_status()

    def _webui_status(self) -> dict[str, object]:
        """Implement the webui status operation for the instance daemon.

        Returns:
            The `dict[str, object]` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._webui_status`. It delegates to `status`
            while keeping intermediate state local to the owning operation.
        """
        if self._webui_server is None:
            return {
                "state": "disabled" if self.webui.mode == "disabled" else "stopped",
                "mode": self.webui.mode,
                "auth_required": self._webui_auth_required(),
            }
        return {**self._webui_server.status(), "mode": self.webui.mode}

    def _webui_auth_required(self) -> bool:
        """Require WebUI authentication outside an explicitly enabled development session.

        Returns:
            Result produced by this callable.

        Notes:
            This helper remains internal to its owning implementation.
        """
        return not self.development.enabled or self.development.webui_require_auth

    async def _start_webui(self) -> None:
        """Start webui.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._start_webui`. It delegates to `cast`,
            `start`, `create_task`, `_watch_broker_diagnostics` while keeping intermediate state local to
            the owning operation.
        """
        if self._webui_server is not None:
            return
        try:
            from liteyukibot_webui import WebUiServer, WebUiUploadPolicy
        except ModuleNotFoundError as error:
            raise RuntimeError("WebUI support is not installed; install `liteyukibot-v7[webui]`") from error
        self._webui_server = WebUiServer(
            cast(Any, self),
            host="127.0.0.1",
            port=self.webui.port,
            session_idle_seconds=self.webui.session_idle_seconds,
            session_max_seconds=self.webui.session_max_seconds,
            require_auth=self._webui_auth_required(),
            upload_staging_directory=self.paths.workspace / ".liteyuki" / "webui" / "staging",
            upload_policy=WebUiUploadPolicy(
                enabled=self.webui.uploads_enabled,
                max_bytes=self.webui.uploads_max_bytes,
                extensions=self.webui.uploads_extensions,
                media_types=self.webui.uploads_media_types,
            ),
        )
        await self._webui_server.start()
        if self._broker_diagnostics is not None and self._broker_watch_task is None:
            self._broker_watch_task = asyncio.create_task(
                self._watch_broker_diagnostics(), name="webui-broker-diagnostics"
            )

    async def _stop_webui(self) -> None:
        """Stop webui.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._stop_webui`. It delegates to `cancel`,
            `gather`, `stop`, `clear` while keeping intermediate state local to the owning operation.
        """
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
        """Implement the issue ticket operation for the instance daemon.

        Returns:
            The `str` result produced by the operation.
        """
        ticket = secrets.token_urlsafe(32)
        self._webui_tickets[ticket] = monotonic() + self.webui.ticket_ttl_seconds
        return ticket

    async def redeem_ticket(self, ticket: str) -> Any:
        """Redeem ticket.

        Args:
            ticket: The ticket value used by the operation.

        Returns:
            The `Any` result produced by the operation.
        """
        expiry = self._webui_tickets.pop(ticket, None)
        if expiry is None or expiry < monotonic():
            return None
        from liteyukibot_webui import WebUiPrincipal

        return WebUiPrincipal(f"daemon:{self.paths.name}", frozenset({"liteyukibot.management.admin"}))

    async def authorize_session(self, principal: Any) -> bool:
        """Authorize session.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            Whether the requested condition is satisfied.
        """
        return (
            getattr(principal, "subject", None) == f"daemon:{self.paths.name}"
            and "liteyukibot.management.admin" in getattr(principal, "capabilities", ())
            and not self._stop_event.is_set()
        )

    async def bootstrap(self, _principal: Any) -> dict[str, object]:
        """Implement the bootstrap operation for the instance daemon.

        Args:
            _principal: The principal value used by the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.
        """
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
        """Implement the presentation operation for the instance daemon.

        Args:
            _principal: The principal value used by the operation.
            locale: The locale value used by the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.
        """
        request = {"locale": locale} if locale is not None else {}
        value = await self._worker_webui_control("daemon.webui.presentation", **request)
        return value if isinstance(value, dict) else {"locale": "en-US", "locales": [], "messages": {}}

    async def snapshot(self, _principal: Any) -> dict[str, object]:
        """Return an immutable snapshot of the instance daemon state.

        Args:
            _principal: The principal value used by the operation.

        Returns:
            The requested `dict[str, object]` value.
        """
        value = await self._worker_webui_control("daemon.webui.snapshot")
        return value if isinstance(value, dict) else {"state": "worker_unavailable"}

    async def logs(
        self, _principal: Any, cursor: str | None, limit: int, level: str | None,
        component: str | None, query: str
    ) -> dict[str, object]:
        """Return the bounded in-process Yukilog projection.

        Args:
            _principal: Input accepted by this callable.
            cursor: Input accepted by this callable.
            limit: Input accepted by this callable.
            level: Input accepted by this callable.
            component: Input accepted by this callable.
            query: Input accepted by this callable.

        Returns:
            Result produced by this callable.
        """
        from .logging import get_webui_logs

        return get_webui_logs(cursor=cursor, limit=limit, level=level, component=component, query=query)

    async def event_summary(
        self, principal: Any, start: str | None, end: str | None, group_by: str
    ) -> dict[str, object]:
        """Return chart-ready aggregates over the existing bounded delivery projection.

        Args:
            principal: Input accepted by this callable.
            start: Input accepted by this callable.
            end: Input accepted by this callable.
            group_by: Input accepted by this callable.

        Returns:
            Result produced by this callable.
        """
        page = await self.event_deliveries(principal, {}, None, 500)
        raw_items = page.get("items", []) if isinstance(page, Mapping) else []
        items = raw_items if isinstance(raw_items, list) else []
        totals = {"received": len(items), "delivered": 0, "failed": 0, "pending": 0}
        breakdown: dict[str, int] = {}
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, Mapping):
                continue
            status = str(item.get("status", "unknown"))
            breakdown[status] = breakdown.get(status, 0) + 1
            if status == "delivered":
                totals["delivered"] += 1
            elif status in {"failed", "dead_letter"}:
                totals["failed"] += 1
            else:
                totals["pending"] += 1
        return {
            "window": {"from": start, "to": end}, "totals": totals, "series": [],
            "breakdown": [{"key": k, "value": v} for k, v in sorted(breakdown.items())],
        }

    async def topology_graph(self, _principal: Any) -> dict[str, object]:
        """Return a deterministic read-only graph derived from the worker topology snapshot.

        Args:
            _principal: Input accepted by this callable.

        Returns:
            Result produced by this callable.
        """
        snapshot = await self._worker_webui_control("daemon.webui.snapshot")
        topology = snapshot.get("topology", {}) if isinstance(snapshot, Mapping) else {}
        nodes: list[dict[str, object]] = [{
            "id": "kernel", "kind": "kernel", "label": self.paths.name,
            "state": "ready", "metadata": {},
        }]
        edges: list[dict[str, object]] = []
        runtimes = topology.get("runtimes", ()) if isinstance(topology, Mapping) else ()
        for item in runtimes if isinstance(runtimes, list) else []:
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                continue
            node_id = f"runtime:{item['id']}"
            health = item.get("health", {})
            state = health.get("state", "configured") if isinstance(health, Mapping) else "configured"
            nodes.append({
                "id": node_id, "kind": "runtime", "label": str(item.get("id")),
                "state": state, "metadata": {"kind": item.get("kind", "")},
            })
            edges.append({
                "id": f"edge:kernel:{node_id}:controls", "source": "kernel", "target": node_id,
                "kind": "controls", "state": "active", "metadata": {},
            })
        return {"generation": 1, "updated_at": None, "nodes": nodes, "edges": edges, "diagnostics": []}

    async def operation_catalog(self, _principal: Any) -> dict[str, object]:
        """Implement the operation catalog operation for the instance daemon.

        Args:
            _principal: The principal value used by the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.
        """
        await self._prepare_webui_operations()
        return {"operations": list(self.operations.catalog(self._webui_management_principal()))}

    async def submit_operation(self, _principal: Any, request: Mapping[str, Any]) -> dict[str, object]:
        """Implement the submit operation operation for the instance daemon.

        Args:
            _principal: The principal value used by the operation.
            request: Validated request object to process.

        Returns:
            The `dict[str, object]` result produced by the operation.
        """
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
        """Implement the operation operation for the instance daemon.

        Args:
            _principal: The principal value used by the operation.
            operation_id: Stable identifier for the operation.

        Returns:
            The `dict[str, object] | None` result produced by the operation.
        """
        record = self.operations.get(operation_id)
        return self._operation_record(record) if record is not None else None

    async def ledger(self, _principal: Any, cursor: str | None, limit: int) -> dict[str, object]:
        """Implement the ledger operation for the instance daemon.

        Args:
            _principal: The principal value used by the operation.
            cursor: Opaque pagination cursor, or `None` for the first page.
            limit: Maximum number of records to return.

        Returns:
            The `dict[str, object]` result produced by the operation.
        """
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
        """Implement the audit operation for the instance daemon.

        Args:
            _principal: The principal value used by the operation.
            cursor: Opaque pagination cursor, or `None` for the first page.
            limit: Maximum number of records to return.

        Returns:
            The `dict[str, object]` result produced by the operation.
        """
        del cursor
        return {
            "items": [self._operation_record(record) for record in self.operations.records(limit)],
            "next_cursor": None,
        }

    async def plugin_surfaces(self, _principal: Any) -> dict[str, object]:
        """Implement the plugin surfaces operation for the instance daemon.

        Args:
            _principal: The principal value used by the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.
        """
        value = await self._worker_webui_control("daemon.webui.plugin_surfaces")
        return value if isinstance(value, dict) else {"generation": 0, "surfaces": [], "diagnostics": []}

    def _webui_preferences_path(self) -> Path:
        """Handle `InstanceDaemon._webui_preferences_path`.

        Returns:
            Result produced by this callable.

        Notes:
            This helper remains internal to its owning implementation.
        """
        return self.paths.root / "configs" / "webui.json"

    async def webui_preferences(self, _principal: Any) -> dict[str, object]:
        """Handle `InstanceDaemon.webui_preferences`.

        Args:
            _principal: Input accepted by this callable.

        Returns:
            Result produced by this callable.
        """
        value = await self._worker_webui_control("daemon.webui.preferences")
        path = self._webui_preferences_path()
        if path.is_file():
            try:
                document = read_document(path)
                if isinstance(document.get("plugin_layout"), str):
                    value = {"plugin_layout": document["plugin_layout"]}
                if isinstance(document.get("followed"), list):
                    value["followed"] = [item for item in document["followed"] if isinstance(item, str)]
                if isinstance(document.get("toast_duration"), int) and document["toast_duration"] in {1500, 3000, 6000}:
                    value["toast_duration"] = document["toast_duration"]
                for key in ("plugin_sources", "disabled_plugin_sources"):
                    if isinstance(document.get(key), list):
                        value[key] = [item for item in document[key] if isinstance(item, str)]
            except (OSError, ValueError, tomllib.TOMLDecodeError):
                pass
        return value if isinstance(value, dict) else {"plugin_layout": "inline"}

    async def update_webui_preferences(self, _principal: Any, request: Mapping[str, object]) -> dict[str, object]:
        """Handle `InstanceDaemon.update_webui_preferences`.

        Args:
            _principal: Input accepted by this callable.
            request: Input accepted by this callable.

        Returns:
            Result produced by this callable.
        """
        layout = request.get("plugin_layout")
        path = self._webui_preferences_path()
        current = await self.webui_preferences(_principal)
        if layout is not None:
            if layout not in {"sidebar", "inline", "main-sidebar"}:
                raise ValueError("invalid WebUI plugin layout")
            current["plugin_layout"] = layout
        followed = request.get("followed")
        if followed is not None:
            if not isinstance(followed, list) or any(not isinstance(item, str) for item in followed):
                raise ValueError("invalid followed plugin list")
            current["followed"] = followed
        toast_duration = request.get("toast_duration")
        if toast_duration is not None:
            if toast_duration not in {1500, 3000, 6000}:
                raise ValueError("invalid WebUI toast duration")
            current["toast_duration"] = toast_duration
        for key in ("plugin_sources", "disabled_plugin_sources"):
            items = request.get(key)
            if items is not None:
                if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
                    raise ValueError(f"invalid {key}")
                current[key] = items
        write_document(path, current)
        if layout is not None:
            await self._worker_webui_control("daemon.webui.preferences.update", plugin_layout=layout)
        return current

    async def plugin_discovery(
        self,
        _principal: Any,
        query: str,
        source_id: str | None,
        runtime_kind: str | None,
        status: str | None,
        refresh: bool,
        cursor: str | None,
        limit: int,
    ) -> dict[str, object]:
        """Search bounded plugin indexes and return metadata-only discovery records.

        Args:
            _principal: Input accepted by this callable.
            query: Input accepted by this callable.
            source_id: Input accepted by this callable.
            runtime_kind: Input accepted by this callable.
            status: Input accepted by this callable.
            refresh: Input accepted by this callable.
            cursor: Input accepted by this callable.
            limit: Input accepted by this callable.

        Returns:
            Result produced by this callable.
        """
        if len(query) > _MAX_PLUGIN_QUERY_LENGTH or not 1 <= limit <= _MAX_PLUGIN_PAGE_SIZE:
            raise ValueError("invalid plugin discovery bounds")
        offset = int(cursor or "0")
        if offset < 0:
            raise ValueError("invalid plugin discovery cursor")
        store = PluginSourceStore(self.paths.workspace)
        sources = tuple(source for source in store.list() if source_id is None or source.id == source_id)
        if not sources:
            raise ValueError("plugin source is not configured")
        source_documents = [_plugin_source_document(source, store.cached_digest(source.id)) for source in sources]
        diagnostics: list[dict[str, object]] = []
        matches: list[dict[str, object]] = []
        normalized_status = None if status in {None, "all"} else status
        for source, source_document in zip(sources, source_documents, strict=True):
            try:
                index = store.fetch(source.id, refresh=refresh)
            except PluginStoreError:
                diagnostics.append({"source_id": source.id, "code": "plugin.source_unavailable"})
                continue
            source_document["cache_state"] = "cached"
            source_document["digest"] = index.digest
            for bundle in index.search(query):
                if normalized_status is not None and bundle.status != normalized_status:
                    continue
                if runtime_kind is not None and runtime_kind not in {facet.runtime_kind for facet in bundle.facets}:
                    continue
                if len(matches) < _MAX_PLUGIN_RESULTS:
                    matches.append(
                        {
                            **_plugin_bundle_document(bundle),
                            "source": source.id,
                            "source_priority": source.priority,
                            "official": source.id == OFFICIAL_SOURCE_ID,
                            "index_digest": index.digest,
                        }
                    )
        matches.sort(
            key=lambda item: (
                str(item["bundle_id"]),
                int(cast(int, item["source_priority"])),
                str(item["source"]),
            )
        )
        page = matches[offset : offset + limit]
        next_cursor = str(offset + limit) if offset + limit < len(matches) else None
        return {
            "query": query,
            "filters": {"source_id": source_id, "runtime_kind": runtime_kind, "status": status or "all"},
            "sources": source_documents,
            "items": page,
            "next_cursor": next_cursor,
            "total": min(len(matches), _MAX_PLUGIN_RESULTS),
            "diagnostics": diagnostics,
        }

    async def plugin_details(self, _principal: Any, bundle_id: str, source_id: str) -> dict[str, object]:
        """Handle `InstanceDaemon.plugin_details`.

        Args:
            _principal: Input accepted by this callable.
            bundle_id: Input accepted by this callable.
            source_id: Input accepted by this callable.

        Returns:
            Result produced by this callable.
        """
        store = PluginSourceStore(self.paths.workspace)
        index = store.fetch(source_id)
        selected = index.require(bundle_id)
        project_id = selected.project_id or selected.id
        versions = [bundle for bundle in index.bundles() if (bundle.project_id or bundle.id) == project_id]
        return {
            "project_id": project_id,
            "selected": _plugin_bundle_document(selected),
            "versions": [
                _plugin_bundle_document(bundle)
                for bundle in sorted(versions, key=lambda item: item.version, reverse=True)
            ],
        }

    async def plugin_targets(self, _principal: Any) -> dict[str, object]:
        """Project configured runtime and bridge targets with safe generation summaries.

        Args:
            _principal: Input accepted by this callable.

        Returns:
            Result produced by this callable.
        """
        snapshot = await self._worker_webui_control("daemon.webui.snapshot")
        topology = snapshot.get("topology", {}) if isinstance(snapshot, Mapping) else {}
        runtime_items = topology.get("runtimes", ()) if isinstance(topology, Mapping) else ()
        targets: dict[str, dict[str, object]] = {}
        for item in runtime_items if isinstance(runtime_items, list) else ():
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                continue
            runtime_id = cast(str, item["id"])
            raw_health = item.get("health")
            health = raw_health if isinstance(raw_health, Mapping) else {}
            targets[runtime_id] = {
                "id": runtime_id,
                "kind": item.get("kind", ""),
                "target_type": "runtime",
                "state": health.get("state", "configured"),
            }
        for bridge_id, kind in sorted(self._bridge_kinds.items()):
            targets.setdefault(
                bridge_id,
                {"id": bridge_id, "kind": kind, "target_type": "bridge", "state": "configured"},
            )
        try:
            bridge_definitions = BridgeCatalog().discover()
        except Exception:
            bridge_definitions = {}
        try:
            runtime_definitions, _runtime_diagnostics = RuntimeCatalog().discover_installed()
        except Exception:
            runtime_definitions = {}
        deployment = RuntimeGenerationStore(self.paths.workspace).active()
        result: list[dict[str, object]] = []
        for target_id, target in sorted(targets.items()):
            kind = str(target["kind"])
            bridge = bridge_definitions.get(kind)
            if bridge is not None:
                support_grade = bridge.grade.value
            elif kind in runtime_definitions:
                support_grade = "available"
            else:
                support_grade = "unavailable"
            active_id = deployment.runtime_generations.get(target_id)
            previous_id = deployment.previous.get(target_id)
            store = RuntimeGenerationStore(self.paths.workspace)
            active = store.read(target_id, active_id) if active_id is not None else None
            previous = store.read(target_id, previous_id) if previous_id is not None else None
            active_document = _plugin_generation_document(active)
            enabled_bundle_set: list[object] = []
            if active_document is not None:
                raw_enabled_bundle_set = active_document.get("enabled_bundle_set", [])
                if isinstance(raw_enabled_bundle_set, list):
                    enabled_bundle_set = raw_enabled_bundle_set
            target.update(
                {
                    "support_grade": support_grade,
                    "active_generation": active_document,
                    "previous_generation": _plugin_generation_document(previous),
                    "enabled_bundle_set": enabled_bundle_set,
                    "restart_required": self._restart_plugin_target == target_id,
                }
            )
            result.append(target)
        return {"items": result, "limit": len(result)}

    async def plugin_preview(
        self,
        _principal: Any,
        bundle_id: str,
        source_id: str,
        target_id: str,
    ) -> dict[str, object]:
        """Resolve a target-specific install preview without returning executable inputs.

        Args:
            _principal: Input accepted by this callable.
            bundle_id: Input accepted by this callable.
            source_id: Input accepted by this callable.
            target_id: Input accepted by this callable.

        Returns:
            Result produced by this callable.
        """
        from liteyukibot_webui import WebUiServiceError

        targets = await self.plugin_targets(_principal)
        target_items = targets.get("items", [])
        target = next(
            (item for item in target_items if isinstance(item, Mapping) and item.get("id") == target_id),
            None,
        ) if isinstance(target_items, list) else None
        if not isinstance(target, Mapping):
            raise WebUiServiceError("webui.plugin_target_not_found", 404)
        runtime_kind = target.get("kind")
        if not isinstance(runtime_kind, str):
            raise WebUiServiceError("webui.plugin_target_invalid", 409)
        if target.get("support_grade") not in {"stable", "available"}:
            raise WebUiServiceError("webui.plugin_target_incompatible", 409)
        service = PluginInstallationService(self.paths.workspace)
        try:
            preview = service.preview(bundle_id, source_id=source_id)
            index = service.sources.fetch(source_id, refresh=False)
            if index.digest != preview.index_digest:
                raise PluginStoreError("plugin index changed during preview")
            closure = _resolve_plugin_closure(index, bundle_id)
            target_platform = PlatformTarget.current()
            facets = tuple(bundle.facet_for(runtime_kind, target_platform) for bundle in closure)
        except PluginStoreError as error:
            message = str(error)
            if "yanked" in message:
                raise WebUiServiceError("webui.plugin_yanked", 409) from error
            if "compatible" in message or "no " in message and "facet" in message:
                raise WebUiServiceError("webui.plugin_target_incompatible", 409) from error
            raise WebUiServiceError("webui.plugin_preview_unavailable", 409) from error
        capabilities = sorted({capability for facet in facets for capability in facet.capabilities})
        inputs = tuple(artifact for facet in facets for artifact in (*facet.artifacts, *facet.wheels))
        known_bytes = tuple(artifact.bytes for artifact in inputs)
        exact_bytes = tuple(value for value in known_bytes if value is not None)
        return {
            "source": _plugin_source_document(
                next(source for source in service.sources.list() if source.id == source_id),
                preview.index_digest,
            ),
            "index_digest": preview.index_digest,
            "selected_target": {
                "id": target_id,
                "kind": runtime_kind,
                "support_grade": target.get("support_grade"),
            },
            "bundle": _plugin_bundle_document(preview.bundle),
            "resolved_closure": [_plugin_bundle_document(bundle) for bundle in closure],
            "requested_capabilities": capabilities,
            "download_bytes": sum(exact_bytes) if len(exact_bytes) == len(known_bytes) else None,
            "download_bytes_exact": all(value is not None for value in known_bytes),
            "security": {
                "execution_boundary": "selected_runtime",
                "artifact_bytes_exposed": False,
                "load_plan_exposed": False,
                "credentials_exposed": False,
            },
        }

    async def lyf_resources(self, _principal: Any) -> dict[str, object]:
        """Implement the lyf resources operation for the instance daemon.

        Args:
            _principal: The principal value used by the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.
        """
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
        """Implement the event deliveries operation for the instance daemon.

        Args:
            _principal: The principal value used by the operation.
            filters: Validated filters applied to the result set.
            cursor: Opaque pagination cursor, or `None` for the first page.
            limit: Maximum number of records to return.

        Returns:
            The `dict[str, object]` result produced by the operation.
        """
        if self._broker_diagnostics is None:
            return {
                "broker": {
                    "state": "disabled",
                    "active": 0,
                    "active_capacity": 0,
                    "terminal": 0,
                    "terminal_capacity": 0,
                    "terminal_content_bytes": 0,
                    "terminal_content_bytes_capacity": 0,
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
                    "terminal_content_bytes": 0,
                    "terminal_content_bytes_capacity": 0,
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
                "terminal_content_bytes": status.terminal_content_bytes,
                "terminal_content_bytes_capacity": status.terminal_content_bytes_capacity,
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
        """Implement the event delivery operation for the instance daemon.

        Args:
            _principal: The principal value used by the operation.
            event_id: Stable event identifier.

        Returns:
            The `dict[str, object] | None` result produced by the operation.
        """
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
        """Replay events.

        Args:
            _principal: The principal value used by the operation.
            after_id: Last observed event identifier, or `None` to start at the current boundary.
            limit: Maximum number of records to return.

        Returns:
            The `Any` result produced by the operation.
        """
        from liteyukibot_webui import WebUiEventReplay

        events = tuple(self._webui_events)
        if after_id is None:
            return WebUiEventReplay(events[-limit:])
        for index, event in enumerate(events):
            if event.identifier == after_id:
                return WebUiEventReplay(events[index + 1 :][:limit])
        return WebUiEventReplay((), reset=bool(events))

    async def stream_events(self, _principal: Any, _after_id: str | None) -> AsyncIterator[Any]:
        """Stream events.

        Args:
            _principal: The principal value used by the operation.
            _after_id: Stable identifier for the after.

        Returns:
            Values yielded by the operation.
        """
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
        """Implement the prepare webui operations operation for the instance daemon.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._prepare_webui_operations`. It delegates to
            `_worker_webui_control`, `get`, `register`, `start` while keeping intermediate state local to
            the owning operation.
        """
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
        """Implement the watch broker diagnostics operation for the instance daemon.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._watch_broker_diagnostics`. It delegates to
            `is_set`, `status`, `_publish_webui_event`, `sleep` while keeping intermediate state local to
            the owning operation.
        """
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
        """Execute worker operation.

        Args:
            _principal: The principal value used by the operation.
            request: Validated request object to process.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._execute_worker_operation`. It delegates to
            `_worker_webui_control`, `get`, `cast` while keeping intermediate state local to the owning
            operation.
        """
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
        """Implement the worker webui control operation for the instance daemon.

        Args:
            command: Command or operation name to execute.
            **parameters: The parameters value used by the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._worker_webui_control`. It delegates to
            `cast` while keeping intermediate state local to the owning operation.
        """
        if self.worker_descriptor is None:
            raise RuntimeError("WebUI worker bridge is unavailable")
        return await cast(Any, request_control)(self.worker_descriptor, command, **parameters)

    def _webui_management_principal(self) -> ManagementPrincipal:
        """Implement the webui management principal operation for the instance daemon.

        Returns:
            The `ManagementPrincipal` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._webui_management_principal`. It delegates to
            `frozenset` while keeping intermediate state local to the owning operation.
        """
        return ManagementPrincipal(
            PrincipalKind.WEB_SESSION,
            f"daemon:{self.paths.name}",
            "loopback-webui",
            None,
            frozenset({"liteyukibot.management.admin"}),
        )

    @staticmethod
    def _operation_record(record: OperationRecord) -> dict[str, object]:
        """Implement the operation record operation for the instance daemon.

        Args:
            record: The record value used by the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._operation_record`. It delegates to
            `isoformat` while keeping intermediate state local to the owning operation.
        """
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
        """Implement the ledger status operation for the instance daemon.

        Args:
            record: The record value used by the operation.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._ledger_status`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        if record.state.value == "succeeded":
            return "healthy"
        if record.state.value in {"failed", "unknown"}:
            return "critical"
        return "attention"

    async def _publish_operation_completion(self, operation_id: str) -> None:
        """Publish operation completion.

        Args:
            operation_id: Stable identifier for the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._publish_operation_completion`. It delegates
            to `is_set`, `get`, `_publish_webui_event`, `_operation_record` while keeping intermediate state
            local to the owning operation.
        """
        while not self._stop_event.is_set():
            record = self.operations.get(operation_id)
            if record is None:
                return
            if record.state.value not in {"queued", "running"}:
                await self._publish_webui_event("operation", self._operation_record(record))
                return
            await asyncio.sleep(0.02)

    def _new_webui_event(self, event: str, data: Mapping[str, object]) -> Any:
        """Implement the new webui event operation for the instance daemon.

        Args:
            event: Event associated with the operation.
            data: The data value used by the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._new_webui_event`. It delegates to `cast`
            while keeping intermediate state local to the owning operation.
        """
        from liteyukibot_webui import WebUiEvent

        self._webui_sequence += 1
        return WebUiEvent(event, cast(Any, data), str(self._webui_sequence))

    async def _publish_webui_event(self, event: str, data: Mapping[str, object]) -> None:
        """Publish webui event.

        Args:
            event: Event associated with the operation.
            data: The data value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._publish_webui_event`. It delegates to
            `_new_webui_event`, `append`, `full`, `put_nowait` while keeping intermediate state local to the
            owning operation.
        """
        item = self._new_webui_event(event, data)
        self._webui_events.append(item)
        for queue in tuple(self._webui_subscribers):
            if queue.full():
                continue
            queue.put_nowait(item)

    async def _recover_interrupted_update(self) -> None:
        """Implement the recover interrupted update operation for the instance daemon.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._recover_interrupted_update`. It delegates to
            `load`, `is_terminal`, `_stop_journaled_processes`, `get` while keeping intermediate state local
            to the owning operation.
        """
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
        """Stop journaled processes.

        Args:
            journal: The journal value used by the operation.

        Returns:
            The `tuple[tuple[tuple[str, int], ...], tuple[str, ...]]` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._stop_journaled_processes`. It delegates to
            `_journal_graph_processes`, `getpid`, `_orphan_process_terminator`, `append` while keeping
            intermediate state local to the owning operation.
        """
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
        """Implement the journal graph processes operation for the instance daemon.

        Args:
            journal: The journal value used by the operation.

        Returns:
            The `tuple[tuple[str, int], ...]` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._journal_graph_processes`. It delegates to
            `get`, `extend`, `add`, `append` while keeping intermediate state local to the owning operation.
        """
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
        """Request update.

        Args:
            request: Validated request object to process.

        Returns:
            The `dict[str, object]` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._request_update`. It delegates to `get`,
            `_update_profile` while keeping intermediate state local to the owning operation.
        """
        profile_id = request.get("profile_id")
        if not isinstance(profile_id, str) or not profile_id:
            raise ValueError("update requires a staged profile_id")
        return await self._update_profile(profile_id)

    async def _request_rollback(self, _request: Mapping[str, Any]) -> dict[str, object]:
        """Request rollback.

        Args:
            _request: The request value used by the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._request_rollback`. It delegates to
            `previous`, `_update_profile` while keeping intermediate state local to the owning operation.
        """
        async with self._update_lock:
            profile_id = self.profile_store.previous()
        return await self._update_profile(profile_id)

    async def _update_profile(self, profile_id: str) -> dict[str, object]:
        """Update profile.

        Args:
            profile_id: Stable identifier for the profile.

        Returns:
            The `dict[str, object]` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._update_profile`. It delegates to `active`,
            `read_manifest`, `begin`, `transition` while keeping intermediate state local to the owning
            operation.
        """
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
            if candidate.bundle_tag != "v7.0.0a13" or candidate.bundle_version != "7.0.0a13":
                raise UpdateError("candidate profile is not an Alpha13 verified bundle")
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
        """Implement the drain broker operation for the instance daemon.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._drain_broker`. It delegates to `monotonic`,
            `drain`, `unfreeze`, `sleep` while keeping intermediate state local to the owning operation.
        """
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
        """Freeze kernel.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._freeze_kernel`. It delegates to
            `request_control`, `get` while keeping intermediate state local to the owning operation.
        """
        if self.worker_descriptor is None:
            raise UpdateError("managed update requires the Kernel control descriptor")
        value = await request_control(self.worker_descriptor, "daemon.lifecycle.freeze")
        if not isinstance(value, Mapping) or value.get("frozen") is not True:
            raise UpdateError("Kernel did not acknowledge lifecycle freeze")

    async def _wait_kernel_healthy(self) -> None:
        """Wait for kernel healthy.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._wait_kernel_healthy`. It delegates to
            `monotonic`, `request_control`, `get`, `sleep` while keeping intermediate state local to the
            owning operation.
        """
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
        """Implement the recover failed update operation for the instance daemon.

        Args:
            active: The active value used by the operation.
            profile_switched: The profile switched value used by the operation.
            admission_frozen: The admission frozen value used by the operation.
            kernel_frozen: The kernel frozen value used by the operation.
            error: The error value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._recover_failed_update`. It delegates to
            `unfreeze`, `transition`, `load`, `request_control` while keeping intermediate state local to
            the owning operation.
        """
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
        """Request stop.

        Args:
            _request: The request value used by the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._request_stop`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        self._stop_event.set()
        return {"accepted": True}

    async def _request_restart(self, _request: Mapping[str, Any]) -> dict[str, object]:
        """Request restart.

        Args:
            _request: The request value used by the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._request_restart`. It delegates to `get`,
            `strip` while keeping intermediate state local to the owning operation.
        """
        reason = _request.get("reason", "explicit CLI restart")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("restart reason must be a non-empty string")
        self._last_restart_reason = reason.strip()
        plugin_target = _request.get("plugin_target")
        if plugin_target is not None and (not isinstance(plugin_target, str) or not plugin_target.strip()):
            raise ValueError("plugin restart target must be a non-empty string")
        self._restart_plugin_target = plugin_target.strip() if isinstance(plugin_target, str) else None
        self._restart_event.set()
        return {"accepted": True}

    async def _worker_control(self, request: Mapping[str, Any]) -> Any:
        """Implement the worker control operation for the instance daemon.

        Args:
            request: Validated request object to process.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._worker_control`. It delegates to `get`,
            `startswith`, `removeprefix`, `items` while keeping intermediate state local to the owning
            operation.
        """
        if not self.development.enabled or self.worker_descriptor is None:
            raise PermissionError("development controls are disabled")
        command = request.get("command")
        if not isinstance(command, str) or not command.startswith("dev."):
            raise ValueError("invalid development control command")
        forwarded = command.removeprefix("dev.")
        parameters = {key: value for key, value in request.items() if key not in {"command", "token"}}
        return await request_control(self.worker_descriptor, forwarded, **parameters)

    async def _watch_for_changes(self) -> None:
        """Implement the watch for changes operation for the instance daemon.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._watch_for_changes`. It delegates to
            `_watch_snapshot`, `is_set`, `sleep`, `monotonic` while keeping intermediate state local to the
            owning operation.
        """
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
        """Implement the watch snapshot operation for the instance daemon.

        Returns:
            The `dict[Path, tuple[int, int]]` result produced by the operation.

        Notes:
            Internal implementation detail for `InstanceDaemon._watch_snapshot`. It delegates to `is_dir`,
            `rglob`, `relative_to`, `is_file` while keeping intermediate state local to the owning
            operation.
        """
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
        """Install signal handlers.

        Returns:
            None.

        Notes:
            Internal implementation detail for `InstanceDaemon._install_signal_handlers`. It delegates to
            `get_running_loop`, `add_signal_handler`, `signal` while keeping intermediate state local to the
            owning operation.
        """
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
