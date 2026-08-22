"""Read-only kernel status contract for native plugins."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from .services import ServiceKey

KERNEL_STATUS_SERVICE = ServiceKey("liteyukibot.kernel.status", 1)


def _freeze_states(name: str, states: Mapping[str, str]) -> Mapping[str, str]:
    """Freeze states.

    Args:
        name: Stable name used to identify the value.
        states: The states value used by the operation.

    Returns:
        The `Mapping[str, str]` result produced by the operation.

    Notes:
        Internal implementation detail for `_freeze_states`. It delegates to `items`, `sorted` while
        keeping intermediate state local to the owning operation.
    """
    normalized: dict[str, str] = {}
    for identifier, state in states.items():
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"{name} identifiers must be non-empty strings")
        if not isinstance(state, str) or not state:
            raise ValueError(f"{name} states must be non-empty strings")
        normalized[identifier] = state
    return MappingProxyType(dict(sorted(normalized.items())))


def _freeze_runtime_health(
    values: Mapping[str, Mapping[str, object]],
) -> Mapping[str, Mapping[str, object]]:
    """Freeze runtime health.

    Args:
        values: The values value used by the operation.

    Returns:
        The `Mapping[str, Mapping[str, object]]` result produced by the operation.

    Notes:
        Internal implementation detail for `_freeze_runtime_health`. It delegates to `items`, `sorted`
        while keeping intermediate state local to the owning operation.
    """
    normalized: dict[str, Mapping[str, object]] = {}
    for runtime_id, value in values.items():
        if not isinstance(runtime_id, str) or not runtime_id:
            raise ValueError("runtime health identifiers must be non-empty strings")
        if not isinstance(value, Mapping):
            raise ValueError("runtime health values must be mappings")
        normalized[runtime_id] = MappingProxyType(dict(value))
    return MappingProxyType(dict(sorted(normalized.items())))


@dataclass(frozen=True, slots=True)
class KernelStatusSnapshot:
    """Represent the validated kernel status snapshot contract."""
    version: str
    state: str
    uptime_seconds: float
    plugins: Mapping[str, str] = field(default_factory=dict)
    runtimes: Mapping[str, str] = field(default_factory=dict)
    runtime_health: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    events_outstanding: int = 0

    def __post_init__(self) -> None:
        """Validate and normalize the kernel status snapshot after initialization.

        Returns:
            None.
        """
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
        object.__setattr__(self, "runtime_health", _freeze_runtime_health(self.runtime_health))

    def as_dict(self) -> dict[str, object]:
        """Implement the as dict operation for the kernel status snapshot.

        Returns:
            The `dict[str, object]` result produced by the operation.
        """
        return {
            "version": self.version,
            "state": self.state,
            "uptime_seconds": self.uptime_seconds,
            "plugins": dict(self.plugins),
            "runtimes": dict(self.runtimes),
            "runtime_health": {
                runtime_id: dict(health) for runtime_id, health in self.runtime_health.items()
            },
            "events_outstanding": self.events_outstanding,
        }


class KernelStatusProvider(Protocol):
    """Define the structural interface required from a kernel status provider."""
    def snapshot(self) -> KernelStatusSnapshot:
        """Return an immutable snapshot of the kernel status provider state.

        Returns:
            The requested `KernelStatusSnapshot` value.
        """
        ...


__all__ = [
    "KERNEL_STATUS_SERVICE",
    "KernelStatusProvider",
    "KernelStatusSnapshot",
]
