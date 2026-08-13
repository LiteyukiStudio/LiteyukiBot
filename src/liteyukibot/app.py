"""LiteyukiBot v7 application lifecycle."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

from ._version import __version__
from .agents import (
    AGENT_HISTORY_SERVICE,
    AGENT_TOOL_BROKER_SERVICE,
    AgentToolBroker,
    AgentToolResult,
    EventAgentToolCatalog,
)
from .capabilities import ADAPTER_CALL_API, AGENT_HISTORY_CLEAR, PERMISSION_SERVICE_MAJOR, PERMISSION_SERVICE_NAME
from .config import AppSettings, RuntimeEventRoute
from .control import ControlServer
from .events import ActionEnvelope, ActionResult, CallApi, EventBus, EventEnvelope
from .functions import FUNCTION_DISPATCH_SERVICE, FunctionDispatcher
from .http import HttpServer
from .i18n import I18N_SERVICE, Translator
from .logging import Logger, configure_logging, get_logger, log_payload, shutdown_logging
from .management import MANAGEMENT_SERVICE, KernelManagement, ManagementCaller, ManagementError
from .plugin_store import RuntimeGenerationStore
from .plugins import PluginManager
from .resource_packs import RESOURCE_CATALOG_SERVICE, ResourceCatalog
from .runtime import (
    ActionProvenance,
    ActionSinkResult,
    AgentToolSinkResult,
    JsonValue,
    RuntimeCatalog,
    RuntimeSpec,
    RuntimeSupervisor,
    json_value,
)
from .services import ServiceKey, ServiceRegistry
from .status import KERNEL_STATUS_SERVICE, KernelStatusSnapshot
from .tasks import ManagedTasks


class AppState(StrEnum):
    CREATED = "created"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class ActionService:
    """Route protocol-neutral actions to the runtime that owns the bot."""

    def __init__(
        self,
        supervisor: RuntimeSupervisor,
        action_guard: Callable[[EventEnvelope | None, ActionEnvelope], ActionResult | None],
    ) -> None:
        self._supervisor = supervisor
        self._action_guard = action_guard

    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        guarded = self._action_guard(event, action)
        if guarded is not None:
            return guarded
        try:
            response = await self._supervisor.execute_action(
                action.runtime_id,
                action.action_id,
                action.model_dump(mode="json"),
            )
        except (KeyError, ConnectionError, RuntimeError, TimeoutError) as error:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="RUNTIME_UNAVAILABLE",
                error_message=str(error),
            )
        if response.ok:
            return ActionResult.model_validate(
                {
                    "action_id": action.action_id,
                    "success": True,
                    "data": response.data,
                }
            )
        return ActionResult(
            action_id=action.action_id,
            success=False,
            error_code="RUNTIME_ACTION_FAILED",
            error_message=response.error or "runtime rejected the action",
        )


_PERMISSION_SERVICE = ServiceKey(PERMISSION_SERVICE_NAME, PERMISSION_SERVICE_MAJOR)


class _AppStatusProvider:
    def __init__(self, app: LiteyukiApp) -> None:
        self._app = app

    def snapshot(self) -> KernelStatusSnapshot:
        return self._app.status_snapshot()


class _AgentHistoryProvider:
    def __init__(self, app: LiteyukiApp) -> None:
        self._app = app

    async def clear(self, event: EventEnvelope) -> int:
        return await self._app._clear_agent_history(event)


class LiteyukiApp:
    """Own all v7 services and enforce deterministic startup and shutdown."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        logger: Logger | None = None,
        runtime_secrets: Mapping[str, str] | None = None,
        resource_workspace: str | None = None,
    ) -> None:
        self.settings = settings
        self.resource_workspace = resource_workspace or "."
        self.logger = logger or get_logger(component="core")
        self.state = AppState.CREATED
        self.services = ServiceRegistry()
        self.runtimes = RuntimeSupervisor(
            logger=self.logger,
            event_sink=self._ingest_runtime_event,
            action_sink=self._execute_runtime_action,
            secret_values=runtime_secrets,
        )
        self.runtimes.set_logging_settings(settings.logging)
        self.runtimes.set_management_sink(self._execute_runtime_management)
        self.actions = ActionService(self.runtimes, self._authorize_action)
        core = settings.core
        self.events = EventBus(
            queue_capacity=core.queue_capacity,
            enqueue_timeout=core.enqueue_timeout_seconds,
            handler_timeout=core.handler_timeout_seconds,
            max_concurrent_events=core.max_concurrent_events,
            action_executor=self._execute_event_action,
            logger=self.logger,
        )
        self.plugins = PluginManager(
            services=self.services,
            events=self.events,
            actions=self.actions,
            logger=self.logger,
            data_dir=core.data_dir,
            cache_dir=core.cache_dir,
        )
        self.management = KernelManagement(self, self.resource_workspace, self._request_stop)
        self.control = ControlServer(
            core.data_dir / "control.json",
            status_provider=self.status,
            runtime_restarter=self.runtimes.restart,
        )
        self.http = (
            HttpServer(settings.http.host, settings.http.port, status_provider=self.status)
            if settings.http.enabled
            else None
        )
        self._accepting_events = False
        self._stop_callback: Callable[[], None] | None = None
        self._logging_owned = logger is None
        self._logging_started = False
        self._plugins_setup = False
        self._runtimes_started = False
        self._control_started = False
        self._http_started = False
        self._started_at: float | None = None
        self._stopped_at: float | None = None
        self._runtime_state_directories: dict[str, Any] = {}
        self.resources: ResourceCatalog | None = None
        self.translator: Translator | None = None
        self.functions: FunctionDispatcher | None = None
        self._function_tasks = ManagedTasks("functions", on_failure=self._function_task_failed)
        runtime_plugins = RuntimeCatalog().discover()
        generation_store = RuntimeGenerationStore(self.resource_workspace)
        deployment = generation_store.active()
        for runtime_id, runtime in settings.runtimes.items():
            if not runtime.enabled:
                continue
            state_directory = (core.data_dir / "runtimes" / runtime_id).resolve()
            self._runtime_state_directories[runtime_id] = state_directory
            generation_path: Path | None = None
            command = runtime.command or None
            generation_id = deployment.runtime_generations.get(runtime_id)
            if generation_id is not None:
                generation = generation_store.read(runtime_id, generation_id)
                if generation.runtime_kind != runtime.kind:
                    raise RuntimeError(
                        f"runtime {runtime_id!r} generation kind {generation.runtime_kind!r} "
                        f"does not match {runtime.kind!r}"
                    )
                runtime_plugin = runtime_plugins.get(runtime.kind)
                if runtime_plugin is None:
                    raise RuntimeError(f"runtime {runtime.kind!r} has a managed generation but is not installed")
                if runtime.command:
                    raise RuntimeError(
                        f"runtime {runtime_id!r} cannot combine a managed generation with command override"
                    )
                generation_path = generation_store.path_for(runtime_id, generation_id)
                python = generation_store.python_path(generation_path)
                if not python.is_file():
                    raise RuntimeError(f"runtime {runtime_id!r} generation has no Python executable")
                command = (str(python), *runtime_plugin.command[1:])
            self.runtimes.add(
                RuntimeSpec(
                    id=runtime_id,
                    kind=runtime.kind,
                    options=runtime.options,
                    command=command,
                    working_directory=runtime.working_directory,
                    env={
                        **runtime.env,
                        "LITEYUKI_RUNTIME_STATE_DIR": str(state_directory),
                        **({"LITEYUKI_RUNTIME_GENERATION_DIR": str(generation_path)} if generation_path else {}),
                    },
                    secret_env=runtime.secret_env,
                    handshake_timeout=runtime.handshake_timeout_seconds,
                    restart_limit=runtime.max_failures,
                    restart_window=runtime.failure_window_seconds,
                    ready_timeout=runtime.ready_timeout_seconds,
                    heartbeat_interval=runtime.heartbeat_interval_seconds,
                    stale_after=runtime.stale_after_seconds,
                    max_inbound_events=runtime.max_inbound_events,
                    agent_harness=(
                        runtime_plugins[runtime.kind].agent_harness if runtime.kind in runtime_plugins else None
                    ),
                )
            )
        self._runtime_event_routes = self._event_routes(settings)
        if self._runtime_event_routes:
            self.events.subscribe(
                self._forward_runtime_event,
                name="runtime.routes",
            )
        self.services.provide(
            KERNEL_STATUS_SERVICE,
            _AppStatusProvider(self),
            provider="liteyukibot.kernel",
        )
        self.services.provide(
            AGENT_HISTORY_SERVICE,
            _AgentHistoryProvider(self),
            provider="liteyukibot.kernel",
        )
        self.services.provide(MANAGEMENT_SERVICE, self.management, provider="liteyukibot.kernel")

    def set_stop_callback(self, callback: Callable[[], None]) -> None:
        """Bind the host-owned shutdown signal used by the management console."""

        self._stop_callback = callback

    def _request_stop(self) -> None:
        if self._stop_callback is None:
            raise RuntimeError("application host does not support management shutdown")
        self._stop_callback()

    async def start(self) -> None:
        if self.state is not AppState.CREATED:
            raise RuntimeError(f"application cannot start from state {self.state}")
        self.state = AppState.STARTING
        self._started_at = monotonic()
        self._stopped_at = None
        try:
            if self._logging_owned:
                self.logger = configure_logging(self.settings.logging)
                self.runtimes.logger = self.logger
                self.plugins.logger = self.logger
                self._logging_started = True
            self.settings.core.data_dir.mkdir(parents=True, exist_ok=True)
            self.settings.core.cache_dir.mkdir(parents=True, exist_ok=True)
            for state_directory in self._runtime_state_directories.values():
                state_directory.mkdir(parents=True, exist_ok=True)
            await self.events.start()

            definitions = self.plugins.discover(
                self.settings.plugins.enabled,
                self.settings.plugins.local_modules,
            )
            declarations = tuple(
                declaration
                for definition in definitions.values()
                for declaration in definition.manifest.resource_packs
            )
            self.resources = ResourceCatalog.load(self.resource_workspace, plugin_packs=declarations)
            self.translator, _warning = Translator.from_resources(self.resources, self.settings.i18n.locale)
            self.functions = FunctionDispatcher(self.resources, task_owner=self._function_tasks)
            self.services.provide(RESOURCE_CATALOG_SERVICE, self.resources, provider="liteyukibot.kernel")
            self.services.provide(I18N_SERVICE, self.translator, provider="liteyukibot.kernel")
            self.services.provide(FUNCTION_DISPATCH_SERVICE, self.functions, provider="liteyukibot.kernel")
            plugin_configs = self._plugin_configs(self.settings.plugins.config)
            self._plugins_setup = True
            await self.plugins.setup(definitions, plugin_configs)
            permissions = self.services.get(ServiceKey(PERMISSION_SERVICE_NAME, PERMISSION_SERVICE_MAJOR))
            allows_management = getattr(permissions, "allows_management", None)
            if callable(allows_management):
                self.management.registry.set_authorizer(allows_management)
            broker = self.services.get(AGENT_TOOL_BROKER_SERVICE)
            if broker is not None:
                if not isinstance(broker, AgentToolBroker):
                    raise RuntimeError("agent tool broker service has an invalid implementation")
                self.runtimes.set_agent_tool_sink(self._execute_agent_tool)

            await self.runtimes.start()
            self._runtimes_started = True
            await self.plugins.start()

            self._control_started = True
            await self.control.start()
            if self.http is not None:
                self._http_started = True
                await self.http.start()

            self._accepting_events = True
            self.state = AppState.READY
            self.logger.info(
                "LiteyukiBot is ready with {} plugin(s) and {} runtime(s)",
                len(self.plugins.loaded),
                len(self.runtimes.records),
            )
        except BaseException as start_error:
            self.state = AppState.FAILED
            try:
                await self._cleanup()
            except BaseException as cleanup_error:
                start_error.add_note(f"startup cleanup also failed: {cleanup_error}")
            self._freeze_uptime()
            raise

    async def stop(self) -> None:
        if self.state in {AppState.STOPPED, AppState.CREATED}:
            self.state = AppState.STOPPED
            self._freeze_uptime()
            return
        if self.state is AppState.STOPPING:
            return
        self.state = AppState.STOPPING
        try:
            await self._cleanup()
        except BaseException:
            self.state = AppState.FAILED
            raise
        else:
            self.state = AppState.STOPPED
        finally:
            self._freeze_uptime()

    async def run(self) -> None:
        await self.start()
        try:
            await asyncio.Event().wait()
        finally:
            await self.stop()

    async def __aenter__(self) -> LiteyukiApp:
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.stop()

    def status_snapshot(self) -> KernelStatusSnapshot:
        return KernelStatusSnapshot(
            version=__version__,
            state=self.state.value,
            uptime_seconds=self._uptime_seconds(),
            plugins={plugin_id: plugin.state.value for plugin_id, plugin in self.plugins.loaded.items()},
            runtimes={runtime_id: record.state.value for runtime_id, record in self.runtimes.records.items()},
            runtime_health=self.runtimes.health(),
            events_outstanding=self.events.outstanding,
        )

    def status(self) -> dict[str, Any]:
        return self.status_snapshot().as_dict()

    def topology(self, *, discover_plugins: bool = False) -> dict[str, object]:
        """Return a redacted module graph without starting processes or plugins."""

        definitions = (
            self.plugins.discover(self.settings.plugins.enabled, self.settings.plugins.local_modules)
            if discover_plugins
            else {plugin_id: loaded.definition for plugin_id, loaded in self.plugins.loaded.items()}
        )
        runtime_health = self.runtimes.health()
        return {
            "schema_version": 1,
            "kernel": {"version": __version__, "state": self.state.value},
            "services": [
                {"key": str(item.key), "provider": item.provider}
                for item in self.services.snapshot()
            ],
            "plugins": [
                {
                    "id": definition.manifest.id,
                    "name": definition.manifest.name,
                    "version": definition.manifest.version,
                    "api_version": definition.manifest.api_version,
                    "state": self.plugins.loaded[plugin_id].state.value
                    if plugin_id in self.plugins.loaded
                    else "configured",
                    "storage": definition.manifest.storage,
                    "provides": [str(key) for key in definition.manifest.provides],
                    "requires": [
                        {"key": str(requirement.key), "optional": requirement.optional}
                        for requirement in definition.manifest.requires
                    ],
                    "resource_packs": [
                        {"package": pack.package, "root": pack.root}
                        for pack in definition.manifest.resource_packs
                    ],
                }
                for plugin_id, definition in sorted(definitions.items())
            ],
            "runtimes": [
                {
                    "id": runtime_id,
                    "kind": runtime.kind,
                    "enabled": runtime.enabled,
                    "agent_harness": self.runtimes.records[runtime_id].spec.agent_harness
                    if runtime_id in self.runtimes.records
                    else None,
                    "health": runtime_health.get(runtime_id),
                }
                for runtime_id, runtime in sorted(self.settings.runtimes.items())
            ],
            "event_routes": [
                {
                    "sources": list(route.sources),
                    "target": route.target,
                    "messages_only": route.messages_only,
                }
                for route in self._runtime_event_routes
            ],
        }

    def _uptime_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        end = self._stopped_at if self._stopped_at is not None else monotonic()
        return max(0.0, end - self._started_at)

    def _freeze_uptime(self) -> None:
        if self._started_at is not None and self._stopped_at is None:
            self._stopped_at = monotonic()

    async def _cleanup(self) -> None:
        self._accepting_events = False
        errors: list[BaseException] = []
        if self._http_started and self.http is not None:
            try:
                await self.http.stop()
            except BaseException as error:
                errors.append(error)
            self._http_started = False
        if self._control_started:
            try:
                await self.control.stop()
            except BaseException as error:
                errors.append(error)
            self._control_started = False
        try:
            await self.events.aclose()
        except BaseException as error:
            errors.append(error)
        if self._plugins_setup:
            try:
                await self.plugins.stop()
            except BaseException as error:
                errors.append(error)
            self._plugins_setup = False
        if self.functions is not None:
            try:
                await self.functions.aclose()
            except BaseException as error:
                errors.append(error)
        if self._runtimes_started or self.runtimes.records:
            try:
                await self.runtimes.stop()
            except BaseException as error:
                errors.append(error)
            self._runtimes_started = False
        if self._logging_started:
            try:
                shutdown_logging()
            except BaseException as error:
                errors.append(error)
            self._logging_started = False
        if errors:
            raise BaseExceptionGroup("application cleanup failed", errors)

    def _function_task_failed(self, name: str, error: BaseException) -> None:
        self.logger.bind(component="functions").error("function task {} failed: {}", name, error)

    async def _ingest_runtime_event(self, runtime_id: str, payload: dict[str, Any]) -> str:
        log_payload(
            self.logger,
            self.settings.logging,
            operation="runtime.event",
            payload=payload,
            runtime_id=runtime_id,
        )
        if not self._accepting_events:
            return "invalid"
        try:
            event = EventEnvelope.model_validate(payload)
        except ValueError as error:
            self.logger.bind(runtime=runtime_id, component="runtime").warning(
                "runtime event failed validation: {}", error
            )
            return "invalid"
        if event.runtime_id != runtime_id:
            self.logger.bind(runtime=runtime_id, component="runtime").warning(
                "runtime event claimed a different runtime id"
            )
            return "invalid"
        result = await self.events.publish(event)
        return "accepted" if result.status == "processed" else result.status

    async def _execute_runtime_action(
        self,
        source_runtime_id: str,
        payload: dict[str, Any],
        provenance: ActionProvenance | None,
    ) -> ActionSinkResult:
        log_payload(
            self.logger,
            self.settings.logging,
            operation="runtime.action",
            payload=payload,
            runtime_id=source_runtime_id,
        )
        try:
            action = ActionEnvelope.model_validate(payload)
        except ValueError as error:
            self.logger.bind(runtime=source_runtime_id, component="runtime").warning(
                "runtime action failed validation: {}", error
            )
            return ActionSinkResult(ok=False, error="invalid ActionEnvelope")
        if provenance is not None:
            try:
                source_event = EventEnvelope.model_validate(provenance.event_payload)
            except ValueError:
                return ActionSinkResult(ok=False, error="action provenance has an invalid EventEnvelope")
            if (
                action.event_id != source_event.id
                or action.runtime_id != source_event.runtime_id
                or action.bot_id != source_event.bot_id
            ):
                return ActionSinkResult(
                    ok=False,
                    error="child action does not match its source event provenance",
                )
        if action.runtime_id == source_runtime_id:
            return ActionSinkResult(
                ok=False,
                error="child-originated action cannot target its source runtime",
            )
        result = await self.actions.execute(action, event=source_event if provenance is not None else None)
        return ActionSinkResult(
            ok=result.success,
            data=result.model_dump(mode="json"),
            error=result.error_message,
        )

    async def _execute_runtime_management(
        self, runtime_id: str, command: str
    ) -> tuple[bool, str, JsonValue, str | None]:
        caller = ManagementCaller(runtime_id, "runtime", frozenset())
        try:
            _definition, result = await self.management.registry.execute(caller, command)
        except ManagementError as error:
            log_payload(
                self.logger,
                self.settings.logging,
                operation="runtime.management",
                payload={"command": command, "error": str(error)},
                runtime_id=runtime_id,
            )
            return False, "", None, str(error)
        data = json_value(result.data) if result.data is not None else None
        log_payload(
            self.logger,
            self.settings.logging,
            operation="runtime.management",
            payload={"command": command, "result": data if data is not None else result.text},
            runtime_id=runtime_id,
        )
        return True, result.text, data, None

    def _authorize_action(self, event: EventEnvelope | None, action: ActionEnvelope) -> ActionResult | None:
        if not isinstance(action.action, CallApi):
            return None
        if event is None:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="ACTION_PERMISSION_DENIED",
                error_message="adapter API action requires a source event",
            )
        if action.event_id != event.id or action.runtime_id != event.runtime_id or action.bot_id != event.bot_id:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="ACTION_PERMISSION_DENIED",
                error_message="adapter API action does not match its source event",
            )
        permissions = self.services.get(_PERMISSION_SERVICE)
        decide = getattr(permissions, "decide", None)
        allows = getattr(permissions, "allows", None)
        allowed = (
            decide(event, ADAPTER_CALL_API, component="adapter.call_api")
            if callable(decide)
            else callable(allows) and allows(event, ADAPTER_CALL_API)
        )
        if not callable(decide):
            self.logger.bind(
                runtime=event.runtime_id,
                component="permissions",
                capability=ADAPTER_CALL_API,
                event_id=event.id,
                allowed=allowed,
            ).info("adapter API action permission {}", "granted" if allowed else "denied")
        if allowed:
            return None
        return ActionResult(
            action_id=action.action_id,
            success=False,
            error_code="ACTION_PERMISSION_DENIED",
            error_message="adapter API action permission is denied",
        )

    async def _execute_event_action(self, event: EventEnvelope, action: ActionEnvelope) -> ActionResult:
        return await self.actions.execute(action, event=event)

    async def _clear_agent_history(self, event: EventEnvelope) -> int:
        permissions = self.services.get(_PERMISSION_SERVICE)
        decide = getattr(permissions, "decide", None)
        allows = getattr(permissions, "allows", None)
        allowed = (
            decide(event, AGENT_HISTORY_CLEAR, component="agent.history.clear")
            if callable(decide)
            else callable(allows) and allows(event, AGENT_HISTORY_CLEAR)
        )
        if not callable(decide):
            self.logger.bind(
                runtime=event.runtime_id,
                component="permissions",
                capability=AGENT_HISTORY_CLEAR,
                event_id=event.id,
                allowed=allowed,
            ).info("agent history permission {}", "granted" if allowed else "denied")
        if not allowed:
            raise PermissionError("agent history clear permission is denied")

        targets = tuple(
            runtime_id
            for runtime_id, record in self.runtimes.records.items()
            if record.spec.agent_harness == "native"
        )
        if len(targets) != 1:
            raise RuntimeError("native agent history control requires exactly one native agent runtime")
        response = await self.runtimes.execute_control(
            targets[0],
            str(uuid4()),
            "agent.history.clear",
            {
                "runtime_id": event.runtime_id,
                "bot_id": event.bot_id,
                "conversation_id": event.conversation.ordering_key,
            },
        )
        if not response.ok or not isinstance(response.data, dict):
            raise RuntimeError("native agent history clear failed")
        cleared = response.data.get("cleared")
        if not isinstance(cleared, int) or isinstance(cleared, bool) or cleared < 0:
            raise RuntimeError("native agent returned an invalid history clear response")
        return cleared

    def _event_routes(self, settings: AppSettings) -> tuple[RuntimeEventRoute, ...]:
        routes = list(settings.runtime_event_routes)
        configured_targets = {route.target for route in routes}
        runtime_plugins = RuntimeCatalog().discover()
        enabled_ids = tuple(runtime_id for runtime_id, runtime in settings.runtimes.items() if runtime.enabled)
        for runtime_id, runtime in settings.runtimes.items():
            plugin = runtime_plugins.get(runtime.kind)
            if (
                not runtime.enabled
                or runtime_id in configured_targets
                or plugin is None
                or not plugin.default_event_route_messages_only
            ):
                continue
            sources = tuple(source for source in enabled_ids if source != runtime_id)
            if sources:
                routes.append(
                    RuntimeEventRoute(
                        sources=sources,
                        target=runtime_id,
                        messages_only=True,
                    )
                )
        if settings.agent.enabled:
            agent_targets = tuple(
                runtime_id
                for runtime_id, runtime in settings.runtimes.items()
                if runtime.enabled
                and (plugin := runtime_plugins.get(runtime.kind)) is not None
                and plugin.agent_harness == settings.agent.agent_harness
            )
            if not agent_targets:
                raise RuntimeError(
                    f"agent harness {settings.agent.agent_harness!r} is enabled but no matching runtime is installed"
                )
            if len(agent_targets) > 1:
                raise RuntimeError(
                    f"agent harness {settings.agent.agent_harness!r} is ambiguous: {', '.join(agent_targets)}"
                )
            target = agent_targets[0]
            if target not in configured_targets:
                sources = tuple(
                    runtime_id
                    for runtime_id, runtime in settings.runtimes.items()
                    if runtime.enabled
                    and runtime_id != target
                    and (
                        (source_plugin := runtime_plugins.get(runtime.kind)) is None
                        or source_plugin.agent_harness is None
                    )
                )
                if sources:
                    routes.append(
                        RuntimeEventRoute(
                            sources=sources,
                            target=target,
                            messages_only=True,
                        )
                    )
        return tuple(routes)

    async def _execute_agent_tool(
        self,
        _agent_runtime_id: str,
        _delivery_correlation_id: str,
        event_payload: dict[str, Any],
        tool_id: str,
        arguments: dict[str, Any],
    ) -> AgentToolSinkResult:
        broker = self.services.get(AGENT_TOOL_BROKER_SERVICE)
        if broker is None or not isinstance(broker, AgentToolBroker):
            return AgentToolSinkResult(ok=False, error="agent tool broker is unavailable")
        try:
            event = EventEnvelope.model_validate(event_payload)
        except ValueError:
            return AgentToolSinkResult(ok=False, error="agent tool delivery has an invalid EventEnvelope")
        try:
            result = await broker.execute(event, tool_id, arguments)
        except Exception as error:
            self.logger.bind(component="agent").error("agent tool {} failed: {}", tool_id, error)
            return AgentToolSinkResult(ok=False, error="agent tool broker failed")
        if not isinstance(result, AgentToolResult):
            return AgentToolSinkResult(ok=False, error="agent tool broker returned an invalid result")
        return AgentToolSinkResult(ok=result.ok, data=json_value(result.data), error=result.error)

    async def _forward_runtime_event(self, event: EventEnvelope) -> None:
        targets = tuple(
            route.target
            for route in self._runtime_event_routes
            if event.runtime_id in route.sources and (not route.messages_only or event.message is not None)
        )
        if not targets:
            return
        outcomes = await asyncio.gather(
            *(self._deliver_runtime_event(runtime_id, event) for runtime_id in targets),
            return_exceptions=True,
        )
        fatal = next(
            (
                outcome
                for outcome in outcomes
                if isinstance(outcome, BaseException) and not isinstance(outcome, Exception)
            ),
            None,
        )
        if fatal is not None:
            raise fatal
        errors = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        if len(errors) == 1:
            raise errors[0]
        if len(errors) > 1:
            raise ExceptionGroup("runtime event delivery failed", errors)

    async def _deliver_runtime_event(self, runtime_id: str, event: EventEnvelope) -> None:
        catalog: Mapping[str, Any] | None = None
        record = self.runtimes.records[runtime_id]
        if record.spec.agent_harness is not None:
            broker = self.services.get(AGENT_TOOL_BROKER_SERVICE)
            if broker is not None:
                if not isinstance(broker, EventAgentToolCatalog):
                    raise RuntimeError("agent tool broker cannot produce event-scoped catalogs")
                catalog = broker.catalog_for(event)
        if catalog is None:
            result = await self.runtimes.dispatch_event(
                runtime_id,
                event.id,
                event.model_dump(mode="json"),
            )
        else:
            result = await self.runtimes.dispatch_event(
                runtime_id,
                event.id,
                event.model_dump(mode="json"),
                agent_tool_catalog=catalog,
            )
        if result.status != "accepted":
            detail = f": {result.detail}" if result.detail else ""
            raise RuntimeError(f"runtime {runtime_id} rejected event {event.id} as {result.status}{detail}")

    @staticmethod
    def _plugin_configs(config: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        normalized: dict[str, Mapping[str, Any]] = {}
        for plugin_id, value in config.items():
            if not isinstance(value, Mapping):
                raise ValueError(f"plugin config for {plugin_id} must be a mapping")
            normalized[plugin_id] = value
        return normalized


__all__ = ["ActionService", "AppState", "LiteyukiApp"]
