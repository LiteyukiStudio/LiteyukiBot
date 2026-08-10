"""LiteyukiBot v7 application lifecycle."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from enum import StrEnum
from time import monotonic
from typing import Any

from ._version import __version__
from .agents import AGENT_TOOL_BROKER_SERVICE, AgentToolBroker, AgentToolCatalog, AgentToolResult
from .config import AppSettings, RuntimeEventRoute
from .control import ControlServer
from .events import ActionEnvelope, ActionResult, EventBus, EventEnvelope
from .http import HttpServer
from .logging import Logger, configure_logging, get_logger, shutdown_logging
from .plugins import PluginManager
from .runtime import (
    ActionSinkResult,
    AgentToolSinkResult,
    RuntimeCatalog,
    RuntimeSpec,
    RuntimeSupervisor,
    json_value,
)
from .services import ServiceRegistry
from .status import KERNEL_STATUS_SERVICE, KernelStatusSnapshot


class AppState(StrEnum):
    CREATED = "created"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class ActionService:
    """Route protocol-neutral actions to the runtime that owns the bot."""

    def __init__(self, supervisor: RuntimeSupervisor) -> None:
        self._supervisor = supervisor

    async def execute(self, action: ActionEnvelope) -> ActionResult:
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


class _AppStatusProvider:
    def __init__(self, app: LiteyukiApp) -> None:
        self._app = app

    def snapshot(self) -> KernelStatusSnapshot:
        return self._app.status_snapshot()


class LiteyukiApp:
    """Own all v7 services and enforce deterministic startup and shutdown."""

    def __init__(self, settings: AppSettings, *, logger: Logger | None = None) -> None:
        self.settings = settings
        self.logger = logger or get_logger(component="core")
        self.state = AppState.CREATED
        self.services = ServiceRegistry()
        self.runtimes = RuntimeSupervisor(
            logger=self.logger,
            event_sink=self._ingest_runtime_event,
            action_sink=self._execute_runtime_action,
        )
        self.actions = ActionService(self.runtimes)
        core = settings.core
        self.events = EventBus(
            queue_capacity=core.queue_capacity,
            enqueue_timeout=core.enqueue_timeout_seconds,
            handler_timeout=core.handler_timeout_seconds,
            max_concurrent_events=core.max_concurrent_events,
            action_executor=self.actions.execute,
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
        self._logging_owned = logger is None
        self._logging_started = False
        self._plugins_setup = False
        self._runtimes_started = False
        self._control_started = False
        self._http_started = False
        self._started_at: float | None = None
        self._stopped_at: float | None = None
        self._runtime_state_directories: dict[str, Any] = {}
        runtime_plugins = RuntimeCatalog().discover()
        for runtime_id, runtime in settings.runtimes.items():
            if not runtime.enabled:
                continue
            state_directory = (core.data_dir / "runtimes" / runtime_id).resolve()
            self._runtime_state_directories[runtime_id] = state_directory
            self.runtimes.add(
                RuntimeSpec(
                    id=runtime_id,
                    kind=runtime.kind,
                    options=runtime.options,
                    command=runtime.command or None,
                    working_directory=runtime.working_directory,
                    env={
                        **runtime.env,
                        "LITEYUKI_RUNTIME_STATE_DIR": str(state_directory),
                    },
                    handshake_timeout=runtime.handshake_timeout_seconds,
                    restart_limit=runtime.max_failures,
                    restart_window=runtime.failure_window_seconds,
                    ready_timeout=runtime.ready_timeout_seconds,
                    heartbeat_interval=runtime.heartbeat_interval_seconds,
                    stale_after=runtime.stale_after_seconds,
                    max_inbound_events=runtime.max_inbound_events,
                    agent_harness=(
                        runtime_plugins[runtime.kind].agent_harness
                        if runtime.kind in runtime_plugins
                        else None
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
            plugin_configs = self._plugin_configs(self.settings.plugins.config)
            self._plugins_setup = True
            await self.plugins.setup(definitions, plugin_configs)
            broker = self.services.get(AGENT_TOOL_BROKER_SERVICE)
            if broker is not None:
                if not isinstance(broker, AgentToolBroker):
                    raise RuntimeError("agent tool broker service has an invalid implementation")
                self.runtimes.set_agent_tool_sink(self._execute_agent_tool)
                if isinstance(broker, AgentToolCatalog):
                    catalog = broker.catalog()
                    for runtime_id, record in self.runtimes.records.items():
                        if record.spec.agent_harness is not None:
                            self.runtimes.merge_options(runtime_id, {"agent_tool_catalog": catalog})

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
            plugins={
                plugin_id: plugin.state.value for plugin_id, plugin in self.plugins.loaded.items()
            },
            runtimes={
                runtime_id: record.state.value for runtime_id, record in self.runtimes.records.items()
            },
            events_outstanding=self.events.outstanding,
        )

    def status(self) -> dict[str, Any]:
        return self.status_snapshot().as_dict()

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

    async def _ingest_runtime_event(self, runtime_id: str, payload: dict[str, Any]) -> str:
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
        self, source_runtime_id: str, payload: dict[str, Any]
    ) -> ActionSinkResult:
        try:
            action = ActionEnvelope.model_validate(payload)
        except ValueError as error:
            self.logger.bind(runtime=source_runtime_id, component="runtime").warning(
                "runtime action failed validation: {}", error
            )
            return ActionSinkResult(ok=False, error="invalid ActionEnvelope")
        if action.runtime_id == source_runtime_id:
            return ActionSinkResult(
                ok=False,
                error="child-originated action cannot target its source runtime",
            )
        result = await self.actions.execute(action)
        return ActionSinkResult(
            ok=result.success,
            data=result.model_dump(mode="json"),
            error=result.error_message,
        )

    def _event_routes(self, settings: AppSettings) -> tuple[RuntimeEventRoute, ...]:
        routes = list(settings.runtime_event_routes)
        configured_targets = {route.target for route in routes}
        runtime_plugins = RuntimeCatalog().discover()
        enabled_ids = tuple(
            runtime_id for runtime_id, runtime in settings.runtimes.items() if runtime.enabled
        )
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
        result = await self.runtimes.dispatch_event(
            runtime_id,
            event.id,
            event.model_dump(mode="json"),
        )
        if result.status != "accepted":
            detail = f": {result.detail}" if result.detail else ""
            raise RuntimeError(
                f"runtime {runtime_id} rejected event {event.id} as {result.status}{detail}"
            )

    @staticmethod
    def _plugin_configs(config: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        normalized: dict[str, Mapping[str, Any]] = {}
        for plugin_id, value in config.items():
            if not isinstance(value, Mapping):
                raise ValueError(f"plugin config for {plugin_id} must be a mapping")
            normalized[plugin_id] = value
        return normalized


__all__ = ["ActionService", "AppState", "LiteyukiApp"]
