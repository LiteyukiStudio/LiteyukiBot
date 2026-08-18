"""Kernel-agnostic host factory exposed through entry-point metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib import metadata
from inspect import isawaitable
from typing import Any, cast

from liteyukibot.events import EventBus
from liteyukibot.plugins import (
    ExtensionCoexistence,
    ExtensionIdentity,
    ExtensionManifest,
    PluginContext,
    PluginDefinition,
    PluginHandle,
    PluginPaths,
    PluginServices,
    ToolCallback,
    ToolDeclaration,
    _PluginCleanup,
)
from liteyukibot.services import ServiceKey, ServiceRegistry
from liteyukibot.tasks import ManagedTasks

from .audit import CordisAuditService
from .core import ActionServiceLike, CordisManager, PluginFactory
from .scope import Scope

PLUGIN_ENTRY_POINT_GROUP = "liteyukibot.cordis_plugins"


@dataclass(frozen=True, slots=True)
class CordisPluginDefinition:
    """Declarative Cordis Plugin v1 entry-point payload."""

    id: str
    factory: PluginFactory
    coexistence: ExtensionCoexistence = ExtensionCoexistence.EXCLUSIVE
    manifest: ExtensionManifest | None = None

    def __post_init__(self) -> None:
        ExtensionIdentity(self.id, self.coexistence)
        if not callable(self.factory):
            raise TypeError(f"Cordis plugin {self.id!r} factory must be callable")
        if self.manifest is not None and self.manifest.id != self.id:
            raise ValueError("Cordis manifest ID must match its entry-point ID")

    @property
    def identity(self) -> ExtensionIdentity:
        coexistence = self.manifest.coexistence if self.manifest is not None else self.coexistence
        return ExtensionIdentity(self.id, coexistence)

    @property
    def tool_ids(self) -> tuple[str, ...]:
        return () if self.manifest is None else tuple(tool.id for tool in self.manifest.tools)


class CordisHost:
    def __init__(
        self,
        events: EventBus,
        actions: ActionServiceLike,
        *,
        settings: Any,
        logger: Any,
        services: ServiceRegistry | None = None,
        data_dir: Any = None,
        cache_dir: Any = None,
    ) -> None:
        self.manager = CordisManager(events, actions, audit=CordisAuditService(logger=logger))
        self.settings = settings
        self._definitions = discover_cordis_plugins(settings.enabled)
        self._tool_handlers: dict[str, ToolCallback] = {}
        self._native_adapter = _NativeAdapter(
            events,
            actions,
            services=services,
            logger=logger,
            data_dir=data_dir,
            cache_dir=cache_dir,
            access=settings.access,
        )
        self.manager.scope.provide("liteyukibot.native_adapter", lambda: self._native_adapter)

    @property
    def plugin_access(self) -> Mapping[str, str]:
        return {
            plugin_id: "limited" if plugin_id in self.settings.access else "full" for plugin_id in self._definitions
        }

    @property
    def tool_declarations(self) -> tuple[ToolDeclaration, ...]:
        return tuple(
            tool
            for definition in self._definitions.values()
            if definition.manifest
            for tool in definition.manifest.tools
        )

    @property
    def tool_handlers(self) -> Mapping[str, ToolCallback]:
        return {tool_id: cast(ToolCallback, handler) for tool_id, handler in self.manager.tool_handlers.items()}

    @property
    def plugin_identities(self) -> tuple[ExtensionIdentity, ...]:
        return tuple(definition.identity for definition in self._definitions.values())

    async def start(self) -> None:
        for plugin_id in self._activation_order():
            definition = self._definitions[plugin_id]
            config = self.settings.config.get(plugin_id, {})
            await self.manager.activate(
                plugin_id,
                _configured_factory(definition.factory, config),
                declared_tools=definition.tool_ids,
            )
        await self.manager.start()

    def _activation_order(self) -> tuple[str, ...]:
        providers: dict[ServiceKey, str] = {}
        for plugin_id, definition in self._definitions.items():
            for key in definition.manifest.provides if definition.manifest is not None else ():
                current = providers.get(key)
                if current is not None and current != plugin_id:
                    raise RuntimeError(f"Cordis service {key} has multiple providers: {current}, {plugin_id}")
                providers[key] = plugin_id

        dependencies: dict[str, set[str]] = {plugin_id: set() for plugin_id in self._definitions}
        for plugin_id, definition in self._definitions.items():
            if definition.manifest is None:
                continue
            for requirement in definition.manifest.requires:
                provider = providers.get(requirement.key)
                if provider is not None and provider != plugin_id:
                    dependencies[plugin_id].add(provider)

        ordered: list[str] = []
        pending = {plugin_id: set(required) for plugin_id, required in dependencies.items()}
        while pending:
            ready = sorted(plugin_id for plugin_id, required in pending.items() if not required)
            if not ready:
                raise RuntimeError(f"Cordis plugin service dependency cycle: {', '.join(sorted(pending))}")
            for plugin_id in ready:
                ordered.append(plugin_id)
                del pending[plugin_id]
                for required in pending.values():
                    required.discard(plugin_id)
        return tuple(ordered)

    async def aclose(self) -> None:
        await self.manager.aclose()


def host_factory(
    events: EventBus,
    actions: ActionServiceLike,
    *,
    settings: Any,
    logger: Any,
    services: ServiceRegistry | None = None,
    data_dir: Any = None,
    cache_dir: Any = None,
    **_kwargs: Any,
) -> CordisHost:
    return CordisHost(
        events,
        actions,
        settings=settings,
        logger=logger,
        services=services,
        data_dir=data_dir,
        cache_dir=cache_dir,
    )


class _NativeAdapter:
    def __init__(
        self,
        events: EventBus,
        actions: ActionServiceLike,
        *,
        services: ServiceRegistry | None,
        logger: Any,
        data_dir: Any,
        cache_dir: Any,
        access: Mapping[str, str],
    ) -> None:
        self.events = events
        self.actions = actions
        self.services = services
        self.logger = logger
        self.data_dir = data_dir
        self.cache_dir = cache_dir
        self.access = access

    async def activate(self, scope: Scope, plugin_id: str) -> None:
        if self.services is None:
            raise RuntimeError("Cordis business plugins require the application service registry")
        services = self.services
        entry = next(
            (item for item in metadata.entry_points(group="liteyukibot.plugins") if item.name == plugin_id),
            None,
        )
        if entry is None:
            raise RuntimeError(f"Cordis business plugin {plugin_id!r} has no Native definition")
        candidate = entry.load()
        if not isinstance(candidate, PluginDefinition):
            raise TypeError(f"Native entry point {plugin_id!r} is not a PluginDefinition")
        definition = candidate
        manifest = definition.manifest
        if manifest.id != plugin_id:
            raise RuntimeError(f"Native plugin manifest ID {manifest.id!r} does not match {plugin_id!r}")
        full_access = plugin_id not in self.access
        if not full_access and manifest.capabilities:
            authorizer = services.get(ServiceKey("liteyukibot.permissions", 2))
            activation_allowed = getattr(authorizer, "activation_allowed", None)
            if not callable(activation_allowed) or not activation_allowed(
                manifest.id, frozenset(manifest.capabilities)
            ):
                raise RuntimeError(f"extension {manifest.id} requested capabilities outside its configured ceiling")
        plugin_logger = self.logger.bind(plugin=plugin_id, component="cordis-plugin")
        tasks = ManagedTasks(plugin_id)
        paths = None
        if manifest.storage == "private":
            if self.data_dir is None or self.cache_dir is None:
                raise RuntimeError("Cordis private plugin storage is unavailable")
            paths = PluginPaths(self.data_dir / "plugins" / plugin_id, self.cache_dir / "plugins" / plugin_id)
            paths.data.mkdir(parents=True, exist_ok=True)
            paths.cache.mkdir(parents=True, exist_ok=True)
        cleanup = _PluginCleanup()
        tool_handlers: dict[str, ToolCallback] = {}
        context = PluginContext(
            id=plugin_id,
            config=scope.config,
            logger=plugin_logger,
            services=PluginServices(manifest, services),
            tasks=tasks,
            events=self.events,
            actions=self.actions,
            paths=paths,
            _manifest=manifest,
            _cleanup=cleanup,
            _tool_handlers=tool_handlers,
        )
        handle: PluginHandle = PluginHandle()
        try:
            handle = await definition.setup(context) or handle
            context.services.validate_provided()
            declared = {tool.id for tool in manifest.tools}
            if set(tool_handlers) != declared:
                raise RuntimeError(f"Cordis plugin {plugin_id!r} must register every declared Tool")
            for tool_id, handler in tool_handlers.items():
                scope.tool(tool_id, handler)
            if handle.start is not None:
                await handle.start()
        except BaseException:
            try:
                if handle.stop is not None:
                    await handle.stop()
            finally:
                try:
                    await cleanup.close()
                finally:
                    try:
                        await tasks.stop()
                    finally:
                        services.remove_provider(plugin_id)
            raise

        async def close() -> None:
            try:
                if handle.stop is not None:
                    await handle.stop()
            finally:
                try:
                    await cleanup.close()
                finally:
                    await tasks.stop()
                    services.remove_provider(plugin_id)

        scope.own(close)


def discover_cordis_plugins(enabled: tuple[str, ...]) -> dict[str, CordisPluginDefinition]:
    """Resolve enabled declarative definitions without activating plugin code."""

    entry_points: dict[str, metadata.EntryPoint] = {}
    for entry in metadata.entry_points(group=PLUGIN_ENTRY_POINT_GROUP):
        if entry.name in entry_points:
            raise RuntimeError(f"Cordis plugin entry point {entry.name!r} is duplicated")
        entry_points[entry.name] = entry

    definitions: dict[str, CordisPluginDefinition] = {}
    for plugin_id in enabled:
        configured_entry = entry_points.get(plugin_id)
        if configured_entry is None:
            raise RuntimeError(f"Cordis plugin {plugin_id!r} is not installed")
        try:
            definition = _coerce_definition(configured_entry.load())
        except Exception as error:
            raise RuntimeError(f"Cordis plugin {plugin_id!r} could not be imported") from error
        if definition.id != plugin_id:
            raise RuntimeError(f"Cordis plugin entry point {plugin_id!r} declared mismatched id {definition.id!r}")
        if plugin_id in definitions:
            raise RuntimeError(f"Cordis plugin {plugin_id!r} is duplicated")
        definitions[plugin_id] = definition
    return definitions


def _coerce_definition(candidate: object) -> CordisPluginDefinition:
    if not isinstance(candidate, CordisPluginDefinition):
        raise TypeError("Cordis plugin entry point must resolve to CordisPluginDefinition")
    return candidate


def _configured_factory(factory: PluginFactory, config: Mapping[str, object]) -> PluginFactory:
    async def activate(scope: Scope) -> None:
        configured = scope.child(config=config)
        try:
            result = factory(configured)
            if isawaitable(result):
                await result
        except BaseException:
            await configured.aclose()
            raise

    return activate
