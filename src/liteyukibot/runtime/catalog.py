"""Discovery for separately distributed supervised runtime hosts."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib import metadata

from ..init_specs import RuntimeInitSpec


@dataclass(frozen=True, slots=True)
class RuntimePlugin:
    """One installed runtime host and its executable child command."""

    kind: str
    command: tuple[str, ...]
    default_event_route_messages_only: bool = False
    agent_harness: str | None = None
    init_spec: RuntimeInitSpec | None = None

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
        plugins, diagnostics = self.discover_installed()
        if diagnostics:
            raise RuntimeError("; ".join(diagnostics))
        return plugins

    def discover_installed(self) -> tuple[dict[str, RuntimePlugin], tuple[str, ...]]:
        """Return valid runtime packages plus diagnostics for broken entry points."""

        plugins: dict[str, RuntimePlugin] = {}
        diagnostics: list[str] = []
        for entry in metadata.entry_points(group=self.ENTRY_POINT_GROUP):
            try:
                loaded = entry.load()
                if not callable(loaded):
                    raise TypeError("entry point is not callable")
                plugin = loaded()
                if not isinstance(plugin, RuntimePlugin):
                    raise TypeError("entry point did not return RuntimePlugin")
                if plugin.kind != entry.name:
                    raise ValueError(f"returned mismatched kind {plugin.kind!r}")
                if plugin.kind in plugins:
                    raise ValueError("duplicates an installed runtime kind")
                plugins[plugin.kind] = plugin
            except Exception as error:
                diagnostics.append(f"runtime {entry.name!r} is unavailable: {type(error).__name__}: {error}")
        return plugins, tuple(diagnostics)


__all__ = ["RuntimeCatalog", "RuntimePlugin"]
