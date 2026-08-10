"""Read-only kernel status contract for native plugins."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from .services import ServiceKey

KERNEL_STATUS_SERVICE = ServiceKey("liteyukibot.kernel.status", 1)


def _freeze_states(name: str, states: Mapping[str, str]) -> Mapping[str, str]:
    normalized: dict[str, str] = {}
    for identifier, state in states.items():
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"{name} identifiers must be non-empty strings")
        if not isinstance(state, str) or not state:
            raise ValueError(f"{name} states must be non-empty strings")
        normalized[identifier] = state
    return MappingProxyType(dict(sorted(normalized.items())))


@dataclass(frozen=True, slots=True)
class KernelStatusSnapshot:
    version: str
    state: str
    uptime_seconds: float
    plugins: Mapping[str, str] = field(default_factory=dict)
    runtimes: Mapping[str, str] = field(default_factory=dict)
    events_outstanding: int = 0

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("kernel version must not be empty")
        if not self.state:
            raise ValueError("kernel state must not be empty")
        if self.uptime_seconds < 0:
            raise ValueError("kernel uptime must not be negative")
        if self.events_outstanding < 0:
            raise ValueError("outstanding event count must not be negative")
        object.__setattr__(self, "plugins", _freeze_states("plugin", self.plugins))
        object.__setattr__(self, "runtimes", _freeze_states("runtime", self.runtimes))

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "state": self.state,
            "uptime_seconds": self.uptime_seconds,
            "plugins": dict(self.plugins),
            "runtimes": dict(self.runtimes),
            "events_outstanding": self.events_outstanding,
        }


class KernelStatusProvider(Protocol):
    def snapshot(self) -> KernelStatusSnapshot: ...


__all__ = [
    "KERNEL_STATUS_SERVICE",
    "KernelStatusProvider",
    "KernelStatusSnapshot",
]
