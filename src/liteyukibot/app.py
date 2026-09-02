"""Local LiteyukiBot application composition."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import Awaitable, Callable, Iterable, Mapping
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import Any, Protocol, cast

from liteyukibot_kernel import (
    KERNEL_STATUS_SERVICE,
    ActionBackend,
    ActionEnvelope,
    ActionResult,
    ActionService,
    EventBus,
    EventEnvelope,
    KernelStatusSnapshot,
    ServiceKey,
    ServiceRegistry,
)

from ._version import __version__
from .config import AppSettings
from .i18n import I18N_SERVICE, Translator
from .logging import Logger, configure_logging, get_logger, shutdown_logging
from .resource_packs import ResourceCatalog, ResourcePackDeclaration


def _is_async_callable(value: object) -> bool:
    """Return whether a callback is an async function or async callable object."""

    if inspect.iscoroutinefunction(value):
        return True
    return callable(value) and inspect.iscoroutinefunction(cast(Any, value).__call__)


class AppState(StrEnum):
    """Lifecycle states for the foreground application."""

    CREATED = "created"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class _CordisManager(Protocol):
    """Small structural interface used to keep Cordis optional at import time."""

    scope: Any

    async def start(self) -> None:
        ...

    async def aclose(self) -> None:
        ...


class _AppStatusProvider:
    """Expose the application status through the kernel service contract."""

    def __init__(self, app: LiteyukiApp) -> None:
        self._app = app

    def snapshot(self) -> KernelStatusSnapshot:
        return self._app.status_snapshot()


class LiteyukiApp:
    """Compose the local EventBus, Cordis features, and optional OneBot adapter."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        logger: Logger | None = None,
        resource_workspace: str | Path = ".",
        resource_packs: Iterable[ResourcePackDeclaration] = (),
        action_backend: ActionBackend | None = None,
    ) -> None:
        self.settings = settings
        self.resource_workspace = Path(resource_workspace)
        self.resource_packs = tuple(resource_packs)
        self.logger = logger or get_logger(component="core")
        self.state = AppState.CREATED
        self.services = ServiceRegistry()
        if action_backend is not None and not _is_async_callable(action_backend):
            raise TypeError("action_backend must be an async callable")
        self._action_backend = action_backend
        self.events = EventBus(
            queue_capacity=settings.core.queue_capacity,
            enqueue_timeout=settings.core.enqueue_timeout_seconds,
            handler_timeout=settings.core.handler_timeout_seconds,
            action_timeout=settings.core.action_timeout_seconds,
            close_timeout=settings.core.shutdown_timeout_seconds,
            max_concurrent_events=settings.core.max_concurrent_events,
            max_event_bytes=settings.core.max_event_bytes,
            action_executor=self._execute_event_action,
            logger=self.logger,
        )
        self.actions = ActionService(self._execute_action_backend, self._allow_action)
        self.resources: ResourceCatalog | None = None
        self.translator: Translator | None = None
        self.cordis: _CordisManager | None = None
        self.onebot: object | None = None
        self._feature_states: dict[str, str] = {}
        self._started_at: float | None = None
        self._stopped_at: float | None = None
        self._logging_owned = logger is None
        self._logging_started = False
        self._accepting_events = False
        self._cleanup_tasks: set[asyncio.Task[Any]] = set()
        self._cleanup_operations: dict[str, asyncio.Task[Any]] = {}
        self._lifecycle_lock = asyncio.Lock()
        self._start_operation: asyncio.Task[None] | None = None
        self._stop_operation: asyncio.Task[None] | None = None
        self._runtime_services: list[tuple[ServiceKey, str]] = []
        self.services.provide(KERNEL_STATUS_SERVICE, _AppStatusProvider(self), provider="liteyukibot.kernel")

    async def publish(self, event: EventEnvelope) -> Any:
        """Publish one normalized event to the local EventBus."""
        if not self._accepting_events:
            raise RuntimeError("application is not accepting events")
        return await self.events.publish(event)

    async def start(self) -> None:
        """Start the local kernel and enabled direct features."""
        async with self._lifecycle_lock:
            if self.state is not AppState.CREATED:
                raise RuntimeError(f"application cannot start from state {self.state}")
            self.state = AppState.STARTING
            operation = asyncio.create_task(self._start_impl(), name="liteyukibot-start")
            self._start_operation = operation
            operation.add_done_callback(self._clear_start_operation)
        await asyncio.shield(operation)

    def cancel_start(self) -> None:
        """Request cancellation of a startup task without waiting for its cleanup."""
        operation = self._start_operation
        if operation is not None and not operation.done():
            operation.cancel()

    async def _start_impl(self) -> None:
        """Run startup in a task that cannot be orphaned by caller cancellation."""

        self._started_at = monotonic()
        self._stopped_at = None
        try:
            if self._logging_owned:
                self.logger = configure_logging(self.settings.logging)
                self.events._logger = self.logger
                self._logging_started = True
            self.settings.core.data_dir.mkdir(parents=True, exist_ok=True)
            self.settings.core.cache_dir.mkdir(parents=True, exist_ok=True)
            await self.events.start()
            self.resources = ResourceCatalog.load(
                self.resource_workspace,
                plugin_packs=self.resource_packs,
            )
            self.translator, warning = Translator.from_resources(self.resources, self.settings.i18n.locale)
            self._provide_runtime_service(
                self._resource_service_key(), self.resources, provider="liteyukibot.kernel"
            )
            self._provide_runtime_service(I18N_SERVICE, self.translator, provider="liteyukibot.kernel")
            if warning:
                self.logger.warning("resource locale fallback: {}", warning)
            await self._start_cordis()
            await self._start_onebot()
            self._accepting_events = True
            self.state = AppState.READY
            self.logger.info("LiteyukiBot is ready")
        except BaseException as start_error:
            self.state = AppState.FAILED
            try:
                await self._cleanup()
            except BaseException as cleanup_error:
                start_error.add_note(f"startup cleanup also failed: {cleanup_error}")
            self._freeze_uptime()
            raise

    async def _start_cordis(self) -> None:
        """Activate direct first-party features on one Cordis scope."""
        self.settings.cordis.validate_enabled_config()
        try:
            from liteyukibot_cordis import CordisManager, discover_plugins

            from .features import commands, permissions, profile, resources
            from .features.catalog import activate_builtin_features
        except ImportError as error:
            raise RuntimeError("Cordis is required by enabled local features") from error

        manager = CordisManager(self.events, self.actions)
        self.cordis = cast(_CordisManager, manager)
        providers: dict[object, object] = {
            "liteyukibot.logger": self.logger,
            KERNEL_STATUS_SERVICE: _AppStatusProvider(self),
        }
        if self.translator is not None:
            providers[I18N_SERVICE] = self.translator
        configs = {
            "liteyukibot.permissions": self._feature_config("permissions"),
            "liteyukibot.commands": self._feature_config("commands"),
            "liteyukibot.resources": self._feature_config("resources"),
            "liteyukibot.profile": self._profile_config(),
            "liteyukibot.essentials": self._feature_config("essentials"),
        }
        scopes = await activate_builtin_features(manager, configs=configs, providers=providers)
        active_ids = {scope.plugin_id for scope in scopes}
        self._feature_states = {
            name: "ready" if f"liteyukibot.{name}" in active_ids else "disabled"
            for name in ("permissions", "commands", "resources", "profile", "essentials")
        }
        feature_services = (
            ("liteyukibot.permissions", permissions.PERMISSION_SERVICE),
            ("liteyukibot.commands", commands.COMMAND_SERVICE),
            ("liteyukibot.resources", resources.RESOURCE_SERVICE),
            ("liteyukibot.profile", profile.PROFILE_SERVICE),
        )
        scopes_by_id = {scope.plugin_id: scope for scope in scopes}
        for feature_id, key in feature_services:
            feature_scope = scopes_by_id.get(feature_id)
            if feature_scope is not None:
                self._provide_runtime_service(key, await feature_scope.use(key), provider=feature_id)
        parent = scopes[-1] if scopes else manager.scope
        for plugin_id, factory in discover_plugins(self.settings.cordis.enabled):
            raw_config = self.settings.cordis.config.get(plugin_id, {})
            if not isinstance(raw_config, Mapping):
                raise TypeError(f"cordis.config.{plugin_id} must be a table")
            parent = await manager.activate(plugin_id, factory, config=raw_config, parent=parent)
        await manager.start()

    async def _start_onebot(self) -> None:
        """Start the adapter-owned OneBot service when configured."""
        accounts = self.settings.onebot.v11.accounts
        if not accounts:
            self.logger.warning("OneBot is enabled but no v11 accounts are configured")
            return
        try:
            from liteyukibot_adapter_onebot import OneBotV11Service
        except ImportError as error:
            raise RuntimeError("OneBot is enabled but the adapter package is not installed") from error
        service = OneBotV11Service(
            accounts,
            event_bus=self.events,
            logger=self.logger,
            close_timeout=self.settings.core.shutdown_timeout_seconds,
        )
        self.onebot = service
        if self._action_backend is None:
            self._action_backend = cast(ActionBackend, service.execute)
        await service.start()

    def _feature_config(self, name: str) -> dict[str, object]:
        section = getattr(self.settings, name)
        values = cast(dict[str, object], section.model_dump(mode="json"))
        return values

    def _profile_config(self) -> dict[str, object]:
        values = self._feature_config("profile")
        database = self.settings.profile.database or self.settings.core.data_dir / "profile.sqlite3"
        values["database"] = str(database)
        return values

    @staticmethod
    def _resource_service_key() -> ServiceKey:
        return ServiceKey("liteyukibot.resources.catalog", 1)

    async def _execute_event_action(self, event: EventEnvelope, action: ActionEnvelope) -> ActionResult:
        return await self.actions.execute(action, event=event)

    @staticmethod
    async def _allow_action(_event: EventEnvelope | None, _action: ActionEnvelope) -> None:
        """Allow adapter-owned authorization to remain the host boundary."""

        return None

    async def _execute_action_backend(self, event: EventEnvelope | None, action: ActionEnvelope) -> ActionResult:
        backend = self._action_backend
        if backend is None:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="ACTION_UNAVAILABLE",
                error_message="no adapter action backend is configured",
            )
        result = await backend(event, action)
        if not isinstance(result, ActionResult):
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="ACTION_BACKEND_INVALID",
                error_message="adapter action backend returned an invalid result",
            )
        return result

    def status_snapshot(self) -> KernelStatusSnapshot:
        return KernelStatusSnapshot(
            version=__version__,
            state=self.state.value,
            uptime_seconds=self._uptime_seconds(),
            features=dict(self._feature_states),
            events_outstanding=self.events.outstanding,
        )

    def status(self) -> dict[str, object]:
        snapshot: dict[str, object] = {
            **self.status_snapshot().as_dict(),
            "accepting_events": self._accepting_events,
            "events_background_tasks": self.events.background_tasks,
        }
        if self.onebot is not None:
            status = getattr(self.onebot, "status", None)
            if callable(status):
                snapshot["onebot"] = status()
        return snapshot

    def topology(self) -> dict[str, object]:
        snapshot: dict[str, object] = {
            "schema_version": 1,
            "kernel": {"version": __version__, "state": self.state.value},
            "cordis": {"features": dict(self._feature_states)},
            "services": [{"key": str(item.key), "provider": item.provider} for item in self.services.snapshot()],
        }
        if self.onebot is not None:
            status = getattr(self.onebot, "status", None)
            if callable(status):
                snapshot["onebot"] = status()
        return snapshot

    async def stop(self) -> None:
        """Stop all local services; repeated calls are safe."""
        while True:
            async with self._lifecycle_lock:
                if self.state in {AppState.CREATED, AppState.STOPPED}:
                    self.state = AppState.STOPPED
                    self._freeze_uptime()
                    return
                if self.state is AppState.STARTING:
                    start_operation = self._start_operation
                    stop_operation = None
                    if start_operation is None:
                        self.state = AppState.STOPPING
                        stop_operation = asyncio.create_task(self._stop_impl(), name="liteyukibot-stop")
                        self._stop_operation = stop_operation
                        stop_operation.add_done_callback(self._clear_stop_operation)
                elif self.state is AppState.STOPPING:
                    start_operation = None
                    stop_operation = self._stop_operation
                    if stop_operation is None:
                        stop_operation = asyncio.create_task(self._stop_impl(), name="liteyukibot-stop")
                        self._stop_operation = stop_operation
                        stop_operation.add_done_callback(self._clear_stop_operation)
                else:
                    self.state = AppState.STOPPING
                    start_operation = None
                    stop_operation = asyncio.create_task(self._stop_impl(), name="liteyukibot-stop")
                    self._stop_operation = stop_operation
                    stop_operation.add_done_callback(self._clear_stop_operation)
            if start_operation is not None:
                with contextlib.suppress(BaseException):
                    await asyncio.shield(start_operation)
                continue
            if stop_operation is None:
                continue
            await asyncio.shield(stop_operation)
            return

    async def _stop_impl(self) -> None:
        """Run cleanup in a shared task so concurrent stop callers observe one result."""

        try:
            await self._cleanup()
        except BaseException:
            self.state = AppState.FAILED
            raise
        else:
            self.state = AppState.STOPPED
        finally:
            self._freeze_uptime()

    def _clear_start_operation(self, operation: asyncio.Task[None]) -> None:
        if self._start_operation is operation:
            self._start_operation = None

    def _clear_stop_operation(self, operation: asyncio.Task[None]) -> None:
        if self._stop_operation is operation:
            self._stop_operation = None

    def _provide_runtime_service(self, key: ServiceKey, value: object, *, provider: str) -> None:
        self.services.provide(key, value, provider=provider)
        self._runtime_services.append((key, provider))

    def _remove_runtime_services(self) -> None:
        for key, provider in reversed(self._runtime_services):
            self.services.remove(key, provider=provider)
        self._runtime_services.clear()

    async def _cleanup(self) -> None:
        self._accepting_events = False
        errors: list[BaseException] = []
        deadline = monotonic() + self.settings.core.shutdown_timeout_seconds
        for name, state in self._feature_states.items():
            if state in {"ready", "cleanup_pending"}:
                self._feature_states[name] = "stopping"
        if self.onebot is not None:
            onebot_clean = True
            try:
                close = getattr(self.onebot, "aclose", getattr(self.onebot, "close", None))
                if callable(close):
                    async def invoke_close() -> None:
                        result = close()
                        if inspect.isawaitable(result):
                            await result

                    if not await self._await_cleanup(invoke_close, deadline=deadline, name="OneBot"):
                        onebot_clean = False
                        errors.append(TimeoutError("OneBot cleanup exceeded shutdown deadline"))
            except BaseException as error:
                onebot_clean = False
                errors.append(error)
            if onebot_clean:
                self.onebot = None
        events_clean = True
        try:
            events_clean = await self._await_cleanup(
                self.events.aclose,
                deadline=deadline,
                name="EventBus",
            )
            if self.events.background_tasks:
                events_clean = False
                errors.append(TimeoutError("EventBus left background tasks during shutdown"))
        except BaseException as error:
            events_clean = False
            errors.append(error)
        cordis_clean = self.cordis is None
        if self.cordis is not None and events_clean:
            cordis_clean = True
            try:
                if not await self._await_cleanup(self.cordis.aclose, deadline=deadline, name="Cordis"):
                    cordis_clean = False
                    errors.append(TimeoutError("Cordis cleanup exceeded shutdown deadline"))
            except BaseException as error:
                cordis_clean = False
                errors.append(error)
            if cordis_clean:
                self.cordis = None
        elif self.cordis is not None:
            cordis_clean = False
            errors.append(RuntimeError("Cordis cleanup deferred while EventBus tasks remain"))
        if cordis_clean:
            self._remove_runtime_services()
            for name, state in self._feature_states.items():
                if state in {"stopping", "cleanup_pending"}:
                    self._feature_states[name] = "stopped"
        else:
            for name, state in self._feature_states.items():
                if state == "stopping":
                    self._feature_states[name] = "cleanup_pending"
        if (
            self._logging_started
            and events_clean
            and self.onebot is None
            and self.cordis is None
            and not any(not task.done() for task in self._cleanup_tasks)
        ):
            try:
                shutdown_logging()
            except BaseException as error:
                errors.append(error)
            self._logging_started = False
        if errors:
            raise BaseExceptionGroup("application cleanup failed", errors)

    async def _await_cleanup(
        self,
        operation: Callable[[], Awaitable[Any]],
        *,
        deadline: float,
        name: str,
    ) -> bool:
        """Await one cleanup operation without allowing an uncooperative task to hang shutdown."""

        task = self._cleanup_operations.get(name)
        if task is None or task.done():
            task = asyncio.ensure_future(operation())
            self._cleanup_operations[name] = task
            self._cleanup_tasks.add(task)
            task.add_done_callback(lambda completed: self._cleanup_operation_done(name, completed))
        _, pending = await asyncio.wait((task,), timeout=max(0.0, deadline - monotonic()))
        if pending:
            self.logger.error("{} cleanup exceeded the shutdown deadline", name)
            return False
        task.result()
        return True

    def _cleanup_operation_done(self, name: str, task: asyncio.Task[Any]) -> None:
        if self._cleanup_operations.get(name) is task:
            del self._cleanup_operations[name]
        self._forget_cleanup_task(task)

    def _forget_cleanup_task(self, task: asyncio.Task[Any]) -> None:
        """Forget a completed cleanup task and consume deferred exceptions."""

        self._cleanup_tasks.discard(task)
        if not task.cancelled():
            with contextlib.suppress(BaseException):
                task.exception()

    async def run(self) -> None:
        """Run until the host requests shutdown."""
        await self.start()
        try:
            await asyncio.Event().wait()
        finally:
            await self.stop()

    def _uptime_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        end = self._stopped_at if self._stopped_at is not None else monotonic()
        return max(0.0, end - self._started_at)

    def _freeze_uptime(self) -> None:
        if self._started_at is not None and self._stopped_at is None:
            self._stopped_at = monotonic()


__all__ = ["ActionService", "AppState", "LiteyukiApp"]
