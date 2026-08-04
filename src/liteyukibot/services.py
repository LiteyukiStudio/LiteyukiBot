"""Versioned service contracts shared by native plugins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .exceptions import ServiceError


@dataclass(frozen=True, slots=True, order=True)
class ServiceKey:
    """A stable service name paired with a breaking API generation."""

    name: str
    major: int = 1

    def __post_init__(self) -> None:
        if not self.name or any(part == "" for part in self.name.split(".")):
            raise ValueError("service name must be a non-empty dotted identifier")
        if self.major < 1:
            raise ValueError("service major version must be positive")

    def __str__(self) -> str:
        return f"{self.name}@{self.major}"


@dataclass(frozen=True, slots=True)
class ServiceRequirement:
    key: ServiceKey
    optional: bool = False


@dataclass(frozen=True, slots=True)
class ServiceRegistration:
    key: ServiceKey
    provider: str
    value: Any


class ServiceRegistry:
    """A startup-oriented registry with one provider per service key."""

    def __init__(self) -> None:
        self._services: dict[ServiceKey, ServiceRegistration] = {}

    def provide(self, key: ServiceKey, value: Any, *, provider: str) -> None:
        current = self._services.get(key)
        if current is not None:
            raise ServiceError(
                f"service {key} is already provided by {current.provider}; "
                f"{provider} cannot replace it"
            )
        self._services[key] = ServiceRegistration(key=key, provider=provider, value=value)

    def remove_provider(self, provider: str) -> None:
        for key in [key for key, item in self._services.items() if item.provider == provider]:
            del self._services[key]

    def require(self, key: ServiceKey) -> Any:
        try:
            return self._services[key].value
        except KeyError as exc:
            raise ServiceError(f"required service {key} is unavailable") from exc

    def get(self, key: ServiceKey, default: Any = None) -> Any:
        item = self._services.get(key)
        return default if item is None else item.value

    def provider_for(self, key: ServiceKey) -> str | None:
        item = self._services.get(key)
        return None if item is None else item.provider

    def snapshot(self) -> tuple[ServiceRegistration, ...]:
        return tuple(sorted(self._services.values(), key=lambda item: item.key))
