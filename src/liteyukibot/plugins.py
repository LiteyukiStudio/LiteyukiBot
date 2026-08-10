"""Native v7 plugin definitions and lifecycle management."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from functools import partial
from importlib import import_module, metadata
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from .events import ActionEnvelope, ActionResult, EventBus
from .exceptions import PluginError, ServiceError
from .services import ServiceKey, ServiceRegistry, ServiceRequirement
from .tasks import ManagedTasks


class LoggerLike(Protocol):
    def bind(self, **fields: Any) -> LoggerLike: ...

    def contextualize(self, **fields: Any) -> AbstractContextManager[None]: ...

    def trace(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def info(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def success(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def error(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None: ...


class ActionServiceLike(Protocol):
    async def execute(self, action: ActionEnvelope) -> ActionResult: ...


def _log_task_failure(logger: LoggerLike, name: str, error: BaseException) -> None:
    logger.error("task {} failed: {}", name, error)


class PluginManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    id: str
    name: str
    version: str
    api_version: Literal[1] = 1
    provides: tuple[ServiceKey, ...] = ()
    requires: tuple[ServiceRequirement, ...] = ()
    storage: Literal["none", "private"] = "none"

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if (
            not value
            or value.strip("abcdefghijklmnopqrstuvwxyz0123456789-_.")
            or any(not part for part in value.split("."))
        ):
            raise ValueError("plugin id must use lowercase ASCII letters, digits, '-', '_' or '.'")
        return value

    @field_validator("name", "version")
    @classmethod
    def validate_required_metadata(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("plugin manifest metadata must not be blank")
        return value


PluginCallback = Callable[[], Awaitable[None]]
type CleanupCallback = Callable[[], object]


class _PluginCleanup:
    def __init__(self) -> None:
        self._callbacks: list[CleanupCallback] = []
        self._closed = False

    def defer(self, callback: CleanupCallback) -> None:
        if self._closed:
            raise RuntimeError("plugin cleanup is already closed")
        if not callable(callback):
            raise TypeError("plugin cleanup callback must be callable")
        self._callbacks.append(callback)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        errors: list[BaseException] = []
        while self._callbacks:
            callback = self._callbacks.pop()
            try:
                result = callback()
                if inspect.isawaitable(result):
                    await result
            except BaseException as error:
                errors.append(error)
        if errors:
            raise BaseExceptionGroup("plugin cleanup failed", errors)


@dataclass(frozen=True, slots=True)
class PluginHandle:
    start: PluginCallback | None = None
    stop: PluginCallback | None = None


PluginSetup = Callable[["PluginContext"], Awaitable[PluginHandle | None]]


@dataclass(frozen=True, slots=True)
class PluginDefinition:
    manifest: PluginManifest
    setup: PluginSetup


@dataclass(frozen=True, slots=True)
class PluginPaths:
    data: Path
    cache: Path


class PluginServices:
    def __init__(self, manifest: PluginManifest, registry: ServiceRegistry) -> None:
        self._manifest = manifest
        self._registry = registry
        self._provided: set[ServiceKey] = set()

    def provide(self, key: ServiceKey, value: Any) -> None:
        if key not in self._manifest.provides:
            raise ServiceError(f"plugin {self._manifest.id} did not declare provided service {key}")
        self._registry.provide(key, value, provider=self._manifest.id)
        self._provided.add(key)

    def require(self, key: ServiceKey) -> Any:
        declared = {requirement.key for requirement in self._manifest.requires}
        if key not in declared:
            raise ServiceError(f"plugin {self._manifest.id} did not declare required service {key}")
        return self._registry.require(key)

    def get_optional(self, key: ServiceKey) -> Any | None:
        requirement = next((item for item in self._manifest.requires if item.key == key), None)
        if requirement is None or not requirement.optional:
            raise ServiceError(f"plugin {self._manifest.id} did not declare optional service {key}")
        return self._registry.get(key)

    def validate_provided(self) -> None:
        missing = set(self._manifest.provides) - self._provided
        if missing:
            rendered = ", ".join(str(key) for key in sorted(missing))
            raise ServiceError(f"plugin {self._manifest.id} did not provide declared services: {rendered}")


@dataclass(frozen=True, slots=True)
class PluginContext:
    id: str
    config: Mapping[str, Any]
    logger: LoggerLike
    services: PluginServices
    tasks: ManagedTasks
    events: EventBus
    actions: ActionServiceLike
    paths: PluginPaths | None
    _cleanup: _PluginCleanup = field(repr=False, compare=False)

    def defer_cleanup(self, callback: CleanupCallback) -> None:
        """Run a synchronous or asynchronous callback during plugin cleanup."""

        self._cleanup.defer(callback)


class PluginState(StrEnum):
    DISCOVERED = "discovered"
    SETUP = "setup"
    READY = "ready"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(slots=True)
class LoadedPlugin:
    definition: PluginDefinition
    context: PluginContext
    handle: PluginHandle
    state: PluginState = PluginState.SETUP


class PluginManager:
    ENTRY_POINT_GROUP = "liteyukibot.plugins"

    def __init__(
        self,
        *,
        services: ServiceRegistry,
        events: EventBus,
        actions: ActionServiceLike,
        logger: LoggerLike,
        data_dir: Path,
        cache_dir: Path,
    ) -> None:
        self.services = services
        self.events = events
        self.actions = actions
        self.logger = logger
        self.data_dir = data_dir
        self.cache_dir = cache_dir
        self.loaded: dict[str, LoadedPlugin] = {}

    def discover(
        self, enabled: Sequence[str], local_modules: Sequence[str] = ()
    ) -> dict[str, PluginDefinition]:
        wanted = set(enabled)
        definitions: dict[str, PluginDefinition] = {}
        entry_points = {item.name: item for item in metadata.entry_points(group=self.ENTRY_POINT_GROUP)}
        for plugin_id in sorted(wanted):
            entry_point = entry_points.get(plugin_id)
            if entry_point is None:
                continue
            try:
                candidate = entry_point.load()
            except Exception as error:
                raise PluginError(f"plugin {plugin_id} entry point could not be imported") from error
            self._insert_definition(definitions, self._coerce_definition(candidate), plugin_id)
        for module_name in local_modules:
            try:
                module = import_module(module_name)
                candidate = getattr(module, "plugin", None)
                if candidate is None and callable(getattr(module, "get_plugin", None)):
                    candidate = module.get_plugin()
            except Exception as error:
                raise PluginError(f"local plugin module {module_name} could not be imported") from error
            definition = self._coerce_definition(candidate)
            if definition.manifest.id not in wanted:
                raise PluginError(
                    f"local plugin {definition.manifest.id} is not present in the enabled plugin list"
                )
            self._insert_definition(definitions, definition, definition.manifest.id)
        missing = wanted - definitions.keys()
        if missing:
            raise PluginError(f"enabled plugins were not found: {', '.join(sorted(missing))}")
        return definitions

    @staticmethod
    def _coerce_definition(candidate: Any) -> PluginDefinition:
        if not isinstance(candidate, PluginDefinition):
            raise PluginError("plugin entry point must resolve to PluginDefinition")
        if not inspect.iscoroutinefunction(candidate.setup):
            raise PluginError(f"plugin {candidate.manifest.id} setup must be async")
        return candidate

    @staticmethod
    def _insert_definition(
        definitions: dict[str, PluginDefinition], definition: PluginDefinition, expected_id: str
    ) -> None:
        plugin_id = definition.manifest.id
        if plugin_id != expected_id:
            raise PluginError(f"plugin entry point {expected_id} declared mismatched id {plugin_id}")
        if plugin_id in definitions:
            raise PluginError(f"duplicate plugin id: {plugin_id}")
        definitions[plugin_id] = definition

    def resolve_order(self, definitions: Mapping[str, PluginDefinition]) -> tuple[str, ...]:
        providers: dict[ServiceKey, str] = {}
        for plugin_id, definition in definitions.items():
            for key in definition.manifest.provides:
                existing = providers.get(key) or self.services.provider_for(key)
                if existing is not None:
                    raise PluginError(f"service {key} has multiple providers: {existing}, {plugin_id}")
                providers[key] = plugin_id

        dependencies: dict[str, set[str]] = {plugin_id: set() for plugin_id in definitions}
        for plugin_id, definition in definitions.items():
            for requirement in definition.manifest.requires:
                provider = providers.get(requirement.key) or self.services.provider_for(requirement.key)
                if provider is None:
                    if requirement.optional:
                        continue
                    raise PluginError(f"plugin {plugin_id} requires unavailable service {requirement.key}")
                if provider in definitions and provider != plugin_id:
                    dependencies[plugin_id].add(provider)

        order: list[str] = []
        pending = {plugin_id: set(required) for plugin_id, required in dependencies.items()}
        while pending:
            ready = sorted(plugin_id for plugin_id, required in pending.items() if not required)
            if not ready:
                cycle = ", ".join(sorted(pending))
                raise PluginError(f"plugin service dependency cycle: {cycle}")
            for plugin_id in ready:
                order.append(plugin_id)
                del pending[plugin_id]
                for required in pending.values():
                    required.discard(plugin_id)
        return tuple(order)

    async def setup(
        self,
        definitions: Mapping[str, PluginDefinition],
        configs: Mapping[str, Mapping[str, Any]],
    ) -> None:
        for plugin_id in self.resolve_order(definitions):
            definition = definitions[plugin_id]
            manifest = definition.manifest
            logger = self.logger.bind(plugin=plugin_id, component="plugin")
            tasks = ManagedTasks(
                plugin_id,
                partial(_log_task_failure, logger),
            )
            paths = self._create_paths(plugin_id) if manifest.storage == "private" else None
            plugin_services = PluginServices(manifest, self.services)
            cleanup = _PluginCleanup()
            context = PluginContext(
                id=plugin_id,
                config=MappingProxyType(dict(configs.get(plugin_id, {}))),
                logger=logger,
                services=plugin_services,
                tasks=tasks,
                events=self.events,
                actions=self.actions,
                paths=paths,
                _cleanup=cleanup,
            )
            handle = PluginHandle()
            try:
                handle = await definition.setup(context) or handle
                plugin_services.validate_provided()
            except Exception as exc:
                try:
                    if handle.stop is not None:
                        await handle.stop()
                except BaseException:
                    logger.exception("plugin {} stop after setup failure failed", plugin_id)
                finally:
                    try:
                        await cleanup.close()
                    except BaseException:
                        logger.exception("plugin {} cleanup after setup failure failed", plugin_id)
                    finally:
                        try:
                            await tasks.stop()
                        finally:
                            self.services.remove_provider(plugin_id)
                raise PluginError(f"plugin {plugin_id} setup failed") from exc
            self.loaded[plugin_id] = LoadedPlugin(definition, context, handle)

    async def start(self) -> None:
        for plugin in self.loaded.values():
            if plugin.handle.start is not None:
                await plugin.handle.start()
            plugin.state = PluginState.READY

    async def stop(self) -> None:
        errors: list[BaseException] = []
        for plugin in reversed(tuple(self.loaded.values())):
            try:
                if plugin.handle.stop is not None:
                    await plugin.handle.stop()
            except BaseException as error:
                errors.append(error)
            finally:
                try:
                    await plugin.context._cleanup.close()
                except BaseException as error:
                    errors.append(error)
                try:
                    await plugin.context.tasks.stop()
                except BaseException as error:
                    errors.append(error)
                self.services.remove_provider(plugin.definition.manifest.id)
                plugin.state = PluginState.STOPPED
        if errors:
            raise BaseExceptionGroup("plugin shutdown failed", errors)

    def _create_paths(self, plugin_id: str) -> PluginPaths:
        data = self.data_dir / "plugins" / plugin_id
        cache = self.cache_dir / "plugins" / plugin_id
        data.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        return PluginPaths(data=data, cache=cache)
