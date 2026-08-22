"""Kernel-agnostic host factory exposed through entry-point metadata."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import metadata
from inspect import isawaitable
from typing import Any, cast

from liteyukibot.events import EventBus
from liteyukibot.functions import FunctionHost
from liteyukibot.plugins import (
    ExtensionCoexistence,
    ExtensionIdentity,
    ExtensionManifest,
    PluginContext,
    PluginDefinition,
    PluginEventBus,
    PluginHandle,
    PluginPaths,
    PluginServices,
    ToolCallback,
    ToolDeclaration,
    _default_runtime_context_factory,
    _PluginCleanup,
    _unavailable_runtime_resolver,
)
from liteyukibot.resource_packs import ResourcePackDeclaration
from liteyukibot.runtime_api import RuntimeContextFactory, RuntimeResolver
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
        """Validate and normalize the cordis plugin definition after initialization.

        Returns:
            None.
        """
        ExtensionIdentity(self.id, self.coexistence)
        if not callable(self.factory):
            raise TypeError(f"Cordis plugin {self.id!r} factory must be callable")
        if self.manifest is not None and self.manifest.id != self.id:
            raise ValueError("Cordis manifest ID must match its entry-point ID")

    @property
    def identity(self) -> ExtensionIdentity:
        """Return the cordis plugin definition's identity.

        Returns:
            The `ExtensionIdentity` result produced by the operation.
        """
        coexistence = self.manifest.coexistence if self.manifest is not None else self.coexistence
        return ExtensionIdentity(self.id, coexistence)

    @property
    def tool_ids(self) -> tuple[str, ...]:
        """Return the cordis plugin definition's tool ids.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        return () if self.manifest is None else tuple(tool.id for tool in self.manifest.tools)


class CordisHost:
    """Represent the cordis host contract."""
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
        runtime_context_factory: Callable[[str], RuntimeContextFactory] | None = None,
        runtime_resolver: RuntimeResolver | None = None,
        runtime_targets: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize the cordis host.

        Args:
            events: The events value used by the operation.
            actions: The actions value used by the operation.
            settings: Validated application settings.
            logger: Structured logger used for diagnostics.
            services: The services value used by the operation.
            data_dir: Filesystem path for the data.
            cache_dir: Filesystem path for the cache.
            runtime_context_factory: The runtime context factory value used by the operation.
            runtime_resolver: The runtime resolver value used by the operation.
            runtime_targets: The runtime targets value used by the operation.

        Returns:
            None.
        """
        self.manager = CordisManager(
            events,
            actions,
            audit=CordisAuditService(logger=logger),
            runtime_context_factory=runtime_context_factory,
            runtime_resolver=runtime_resolver,
        )
        self.settings = settings
        self._definitions = discover_cordis_plugins(settings.enabled)
        self._tool_handlers: dict[str, ToolCallback] = {}
        self._function_hosts: dict[str, FunctionHost] = {}
        self._native_adapter = _NativeAdapter(
            events,
            actions,
            services=services,
            logger=logger,
            data_dir=data_dir,
            cache_dir=cache_dir,
            access=settings.access,
            function_hosts=self._function_hosts,
            runtime_context_factory=runtime_context_factory,
            runtime_resolver=runtime_resolver,
            runtime_targets=runtime_targets,
        )
        self.manager.scope.provide("liteyukibot.native_adapter", lambda: self._native_adapter)

    @property
    def plugin_access(self) -> Mapping[str, str]:
        """Return the cordis host's plugin access.

        Returns:
            The `Mapping[str, str]` result produced by the operation.
        """
        return {
            plugin_id: "limited" if plugin_id in self.settings.access else "full" for plugin_id in self._definitions
        }

    @property
    def tool_declarations(self) -> tuple[ToolDeclaration, ...]:
        """Return the cordis host's tool declarations.

        Returns:
            The `tuple[ToolDeclaration, ...]` result produced by the operation.
        """
        return tuple(
            tool
            for definition in self._definitions.values()
            if definition.manifest
            for tool in definition.manifest.tools
        )

    @property
    def tool_handlers(self) -> Mapping[str, ToolCallback]:
        """Return the cordis host's tool handlers.

        Returns:
            The `Mapping[str, ToolCallback]` result produced by the operation.
        """
        return {tool_id: cast(ToolCallback, handler) for tool_id, handler in self.manager.tool_handlers.items()}

    @property
    def function_resource_packs(self) -> Mapping[str, tuple[ResourcePackDeclaration, ...]]:
        """Return the cordis host's function resource packs.

        Returns:
            The `Mapping[str, tuple[ResourcePackDeclaration, ...]]` result produced by the operation.
        """
        return {
            plugin_id: definition.manifest.resource_packs
            for plugin_id, definition in self._definitions.items()
            if definition.manifest is not None and definition.manifest.resource_packs
        }

    @property
    def runtime_manifests(self) -> Mapping[str, ExtensionManifest]:
        """Return the cordis host's runtime manifests.

        Returns:
            The `Mapping[str, ExtensionManifest]` result produced by the operation.
        """
        return {
            plugin_id: definition.manifest
            for plugin_id, definition in self._definitions.items()
            if definition.manifest is not None
        }

    def bind_function_hosts(self, hosts: Mapping[str, FunctionHost]) -> None:
        """Bind function hosts.

        Args:
            hosts: Function hosts keyed by their stable provider identifiers.

        Returns:
            None.
        """
        if self.manager.active_plugin_ids:
            raise RuntimeError("Cordis Function Hosts must be bound before host start")
        self._function_hosts = dict(hosts)
        self._native_adapter.function_hosts = self._function_hosts

    @property
    def plugin_identities(self) -> tuple[ExtensionIdentity, ...]:
        """Return the cordis host's plugin identities.

        Returns:
            The `tuple[ExtensionIdentity, ...]` result produced by the operation.
        """
        return tuple(definition.identity for definition in self._definitions.values())

    async def start(self) -> None:
        """Start the cordis host.

        Returns:
            None.
        """
        for plugin_id in self._activation_order():
            definition = self._definitions[plugin_id]
            config = self.settings.config.get(plugin_id, {})
            await self.manager.activate(
                plugin_id,
                _configured_factory(definition.factory, config, self._function_hosts.get(plugin_id)),
                declared_tools=definition.tool_ids,
                runtime_requirements=() if definition.manifest is None else definition.manifest.runtime_requirements,
            )
        await self.manager.start()

    def _activation_order(self) -> tuple[str, ...]:
        """Implement the activation order operation for the cordis host.

        Returns:
            The `tuple[str, ...]` result produced by the operation.

        Notes:
            Internal implementation detail for `CordisHost._activation_order`. It delegates to `items`,
            `get`, `add`, `sorted` while keeping intermediate state local to the owning operation.
        """
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
        """Close the cordis host asynchronously.

        Returns:
            None.
        """
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
    runtime_context_factory: Callable[[str], RuntimeContextFactory] | None = None,
    runtime_resolver: RuntimeResolver | None = None,
    runtime_targets: Mapping[str, str] | None = None,
) -> CordisHost:
    """Implement the host factory operation for the component.

    Args:
        events: The events value used by the operation.
        actions: The actions value used by the operation.
        settings: Validated application settings.
        logger: Structured logger used for diagnostics.
        services: The services value used by the operation.
        data_dir: Filesystem path for the data.
        cache_dir: Filesystem path for the cache.
        runtime_context_factory: The runtime context factory value used by the operation.
        runtime_resolver: The runtime resolver value used by the operation.
        runtime_targets: The runtime targets value used by the operation.

    Returns:
        The `CordisHost` result produced by the operation.
    """
    return CordisHost(
        events,
        actions,
        settings=settings,
        logger=logger,
        services=services,
        data_dir=data_dir,
        cache_dir=cache_dir,
        runtime_context_factory=runtime_context_factory,
        runtime_resolver=runtime_resolver,
        runtime_targets=runtime_targets,
    )


class _NativeAdapter:
    """Represent the native adapter contract."""
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
        function_hosts: Mapping[str, FunctionHost] | None = None,
        runtime_context_factory: Callable[[str], RuntimeContextFactory] | None = None,
        runtime_resolver: RuntimeResolver | None = None,
        runtime_targets: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize the native adapter.

        Args:
            events: The events value used by the operation.
            actions: The actions value used by the operation.
            services: The services value used by the operation.
            logger: Structured logger used for diagnostics.
            data_dir: Filesystem path for the data.
            cache_dir: Filesystem path for the cache.
            access: The access value used by the operation.
            function_hosts: The function hosts value used by the operation.
            runtime_context_factory: The runtime context factory value used by the operation.
            runtime_resolver: The runtime resolver value used by the operation.
            runtime_targets: The runtime targets value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_NativeAdapter.__init__`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        self.events = events
        self.actions = actions
        self.services = services
        self.logger = logger
        self.data_dir = data_dir
        self.cache_dir = cache_dir
        self.access = access
        self.function_hosts = dict(function_hosts or {})
        self.runtime_context_factory_factory = runtime_context_factory or (
            lambda _extension_id: _default_runtime_context_factory
        )
        self.runtime_resolver = runtime_resolver or _unavailable_runtime_resolver
        self.runtime_targets = dict(runtime_targets or {})

    async def activate(self, scope: Scope, plugin_id: str) -> None:
        """Activate the native adapter operation.

        Args:
            scope: The scope value used by the operation.
            plugin_id: Stable identifier for the plugin.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_NativeAdapter.activate`. It delegates to `next`,
            `entry_points`, `load`, `frozenset` while keeping intermediate state local to the owning
            operation.
        """
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
        requested_capabilities = frozenset((*manifest.capabilities, *manifest.runtime_capabilities))
        if not full_access and requested_capabilities:
            authorizer = services.get(ServiceKey("liteyukibot.permissions", 2))
            activation_allowed = getattr(authorizer, "activation_allowed", None)
            if not callable(activation_allowed) or not activation_allowed(
                manifest.id, requested_capabilities
            ):
                raise RuntimeError(f"extension {manifest.id} requested capabilities outside its configured ceiling")
        missing_runtime_requirements = tuple(
            requirement
            for requirement in manifest.runtime_requirements
            if not requirement.optional
            and not any(
                kind == requirement.runtime
                and (requirement.bridge_id is None or bridge_id == requirement.bridge_id)
                for bridge_id, kind in self.runtime_targets.items()
            )
        )
        if missing_runtime_requirements:
            names = ", ".join(f"{item.runtime}.{item.api}" for item in missing_runtime_requirements)
            raise RuntimeError(f"extension {manifest.id} requires unavailable runtime APIs: {names}")
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
        runtime_context_factory = self.runtime_context_factory_factory(plugin_id)
        context = PluginContext(
            id=plugin_id,
            config=scope.config,
            logger=plugin_logger,
            services=PluginServices(manifest, services),
            tasks=tasks,
            events=PluginEventBus(
                self.events,
                context_factory=runtime_context_factory,
                resolver=self.runtime_resolver,
                requirements=manifest.runtime_requirements,
            ),
            actions=self.actions,
            paths=paths,
            function_host=self.function_hosts.get(plugin_id),
            _manifest=manifest,
            _cleanup=cleanup,
            _tool_handlers=tool_handlers,
            _runtime_context_factory=runtime_context_factory,
            _runtime_resolver=self.runtime_resolver,
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
            """Close the activate and release its owned resources.

            Returns:
                None.

            Notes:
                Internal implementation detail for `_NativeAdapter.activate.close`. It delegates to `stop`,
                `close`, `remove_provider` while keeping intermediate state local to the owning operation.
            """
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
    """Resolve enabled declarative definitions without activating plugin code.

    Args:
        enabled: The enabled value used by the operation.

    Returns:
        The `dict[str, CordisPluginDefinition]` result produced by the operation.
    """

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
    """Implement the coerce definition operation for the component.

    Args:
        candidate: The candidate value used by the operation.

    Returns:
        The `CordisPluginDefinition` result produced by the operation.

    Notes:
        Internal implementation detail for `_coerce_definition`. It performs the local state transition
        directly and is not a stable extension boundary.
    """
    if not isinstance(candidate, CordisPluginDefinition):
        raise TypeError("Cordis plugin entry point must resolve to CordisPluginDefinition")
    return candidate


def _configured_factory(
    factory: PluginFactory,
    config: Mapping[str, object],
    function_host: FunctionHost | None = None,
) -> PluginFactory:
    """Implement the configured factory operation for the component.

    Args:
        factory: The factory value used by the operation.
        config: Validated configuration used by the operation.
        function_host: The function host value used by the operation.

    Returns:
        The `PluginFactory` result produced by the operation.

    Notes:
        Internal implementation detail for `_configured_factory`. It performs the local state transition
        directly and is not a stable extension boundary.
    """
    async def activate(scope: Scope) -> None:
        """Activate the configured factory operation.

        Args:
            scope: The scope value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_configured_factory.activate`. It delegates to `child`,
            `provide`, `factory`, `isawaitable` while keeping intermediate state local to the owning
            operation.
        """
        configured = scope.child(config=config)
        if function_host is not None:
            configured.provide("liteyukibot.function_host", lambda: function_host)
        try:
            result = factory(configured)
            if isawaitable(result):
                await result
        except BaseException:
            await configured.aclose()
            raise

    return activate
