"""Kernel-agnostic host factory exposed through entry-point metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib import metadata
from inspect import isawaitable
from typing import Any

from liteyukibot.events import EventBus
from liteyukibot.plugins import ExtensionCoexistence, ExtensionIdentity

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

    def __post_init__(self) -> None:
        ExtensionIdentity(self.id, self.coexistence)
        if not callable(self.factory):
            raise TypeError(f"Cordis plugin {self.id!r} factory must be callable")

    @property
    def identity(self) -> ExtensionIdentity:
        return ExtensionIdentity(self.id, self.coexistence)


class CordisHost:
    def __init__(self, events: EventBus, actions: ActionServiceLike, *, settings: Any, logger: Any) -> None:
        self.manager = CordisManager(events, actions, audit=CordisAuditService(logger=logger))
        self.settings = settings
        self._definitions = discover_cordis_plugins(settings.enabled)

    @property
    def plugin_identities(self) -> tuple[ExtensionIdentity, ...]:
        return tuple(definition.identity for definition in self._definitions.values())

    async def start(self) -> None:
        for plugin_id, definition in self._definitions.items():
            config = self.settings.config.get(plugin_id, {})
            await self.manager.activate(plugin_id, _configured_factory(definition.factory, config))
        await self.manager.start()

    async def aclose(self) -> None:
        await self.manager.aclose()


def host_factory(
    events: EventBus, actions: ActionServiceLike, *, settings: Any, logger: Any, **_kwargs: Any
) -> CordisHost:
    return CordisHost(events, actions, settings=settings, logger=logger)


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
