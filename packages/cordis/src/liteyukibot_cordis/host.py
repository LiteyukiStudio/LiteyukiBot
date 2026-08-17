"""Kernel-agnostic host factory exposed through entry-point metadata."""

from __future__ import annotations

from collections.abc import Mapping
from importlib import metadata
from inspect import isawaitable
from typing import Any, cast

from liteyukibot.events import EventBus

from .audit import CordisAuditService
from .core import ActionServiceLike, CordisManager, PluginFactory
from .scope import Scope

PLUGIN_ENTRY_POINT_GROUP = "liteyukibot.cordis_plugins"


class CordisHost:
    def __init__(self, events: EventBus, actions: ActionServiceLike, *, settings: Any, logger: Any) -> None:
        self.manager = CordisManager(events, actions, audit=CordisAuditService(logger=logger))
        self.settings = settings

    async def start(self) -> None:
        installed: dict[str, PluginFactory] = {}
        entry_points: dict[str, metadata.EntryPoint] = {}
        for entry in metadata.entry_points(group=PLUGIN_ENTRY_POINT_GROUP):
            if entry.name in entry_points:
                raise RuntimeError(f"Cordis plugin entry point {entry.name!r} is duplicated")
            entry_points[entry.name] = entry
        for plugin_id in self.settings.enabled:
            loaded_entry = entry_points.get(plugin_id)
            if loaded_entry is None:
                raise RuntimeError(f"Cordis plugin {plugin_id!r} is not installed")
            factory = loaded_entry.load()
            if not callable(factory):
                raise RuntimeError(f"Cordis plugin {plugin_id!r} factory is not callable")
            installed[plugin_id] = cast(PluginFactory, factory)
        for plugin_id, factory in installed.items():
            config = self.settings.config.get(plugin_id, {})
            await self.manager.activate(plugin_id, _configured_factory(factory, config))
        await self.manager.start()

    async def aclose(self) -> None:
        await self.manager.aclose()


def host_factory(
    events: EventBus, actions: ActionServiceLike, *, settings: Any, logger: Any, **_kwargs: Any
) -> CordisHost:
    return CordisHost(events, actions, settings=settings, logger=logger)


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
