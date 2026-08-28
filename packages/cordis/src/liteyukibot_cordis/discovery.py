"""Entry-point discovery for explicitly enabled Cordis plugins."""

from __future__ import annotations

from importlib import metadata

from .core import PluginFactory

CORDIS_PLUGIN_ENTRY_POINT_GROUP = "liteyukibot.cordis_plugins"


def discover_plugins(enabled: tuple[str, ...]) -> tuple[tuple[str, PluginFactory], ...]:
    """Load only the named Cordis plugin factories, preserving config order."""

    entries: dict[str, metadata.EntryPoint] = {}
    selected_ids = frozenset(enabled)
    for entry in metadata.entry_points(group=CORDIS_PLUGIN_ENTRY_POINT_GROUP):
        if entry.name not in selected_ids:
            continue
        if entry.name in entries:
            raise RuntimeError(f"duplicate Cordis plugin entry point {entry.name!r}")
        entries[entry.name] = entry

    plugins: list[tuple[str, PluginFactory]] = []
    for plugin_id in enabled:
        selected = entries.get(plugin_id)
        if selected is None:
            raise RuntimeError(f"Cordis plugin {plugin_id!r} is enabled but not installed")
        factory = selected.load()
        if not callable(factory):
            raise TypeError(f"Cordis plugin {plugin_id!r} must expose a callable factory")
        plugins.append((plugin_id, factory))
    return tuple(plugins)


__all__ = ["CORDIS_PLUGIN_ENTRY_POINT_GROUP", "discover_plugins"]
