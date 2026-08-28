"""Read-only application status contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from .services import ServiceKey

KERNEL_STATUS_SERVICE = ServiceKey("liteyukibot.kernel.status", 1)


def _freeze_features(features: Mapping[str, str]) -> Mapping[str, str]:
    normalized: dict[str, str] = {}
    for identifier, state in features.items():
        if not identifier or not state:
            raise ValueError("feature identifiers and states must be non-empty strings")
        normalized[identifier] = state
    return MappingProxyType(dict(sorted(normalized.items())))


@dataclass(frozen=True, slots=True)
class KernelStatusSnapshot:
    version: str
    state: str
    uptime_seconds: float
    features: Mapping[str, str] = field(default_factory=dict)
    events_outstanding: int = 0

    def __post_init__(self) -> None:
        if not self.version or not self.state:
            raise ValueError("status version and state must be non-empty")
        if self.uptime_seconds < 0 or self.events_outstanding < 0:
            raise ValueError("status counters must not be negative")
        object.__setattr__(self, "features", _freeze_features(self.features))

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "state": self.state,
            "uptime_seconds": self.uptime_seconds,
            "features": dict(self.features),
            "events_outstanding": self.events_outstanding,
        }


class KernelStatusProvider(Protocol):
    def snapshot(self) -> KernelStatusSnapshot: ...


__all__ = ["KERNEL_STATUS_SERVICE", "KernelStatusProvider", "KernelStatusSnapshot"]
