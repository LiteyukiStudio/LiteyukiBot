"""Discovery for separately distributed supervised runtime hosts."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib import metadata


@dataclass(frozen=True, slots=True)
class RuntimePlugin:
    """One installed runtime host and its executable child command."""

    kind: str
    command: tuple[str, ...]
    default_event_route_messages_only: bool = False
    agent_harness: str | None = None

    def __post_init__(self) -> None:
        if not self.kind or self.kind != self.kind.strip():
            raise ValueError("runtime plugin kind must be a non-empty trimmed string")
        if not self.command or any(not argument for argument in self.command):
            raise ValueError("runtime plugin command must contain non-empty arguments")
        if self.agent_harness is not None and (
            not self.agent_harness or self.agent_harness != self.agent_harness.strip()
        ):
            raise ValueError("runtime plugin agent_harness must be a non-empty trimmed string")


class RuntimeCatalog:
    """Resolve built-in and entry-point runtime hosts without importing frameworks."""

    ENTRY_POINT_GROUP = "liteyukibot.runtimes"

    def command_for(self, kind: str) -> tuple[str, ...]:
        if kind == "noop":
            return (sys.executable, "-m", "liteyukibot.runtime", "--kind", kind)
        plugin = self.discover().get(kind)
        if plugin is None:
            raise RuntimeError(
                f"runtime kind {kind!r} is not installed; configure an explicit command or install its runtime package"
            )
        return plugin.command

    def discover(self) -> dict[str, RuntimePlugin]:
        plugins: dict[str, RuntimePlugin] = {}
        for entry in metadata.entry_points(group=self.ENTRY_POINT_GROUP):
            loaded = entry.load()
            if not callable(loaded):
                raise RuntimeError(f"runtime entry point {entry.name!r} is not callable")
            plugin = loaded()
            if not isinstance(plugin, RuntimePlugin):
                raise RuntimeError(f"runtime entry point {entry.name!r} did not return RuntimePlugin")
            if plugin.kind != entry.name:
                raise RuntimeError(
                    f"runtime entry point {entry.name!r} returned mismatched kind {plugin.kind!r}"
                )
            if plugin.kind in plugins:
                raise RuntimeError(f"duplicate runtime plugin kind {plugin.kind!r}")
            plugins[plugin.kind] = plugin
        return plugins


__all__ = ["RuntimeCatalog", "RuntimePlugin"]
