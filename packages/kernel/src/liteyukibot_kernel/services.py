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
        """Validate and normalize the service key after initialization.

        Returns:
            None.
        """
        if not self.name or any(part == "" for part in self.name.split(".")):
            raise ValueError("service name must be a non-empty dotted identifier")
        if self.major < 1:
            raise ValueError("service major version must be positive")

    def __str__(self) -> str:
        """Implement the str operation for the service key.

        Returns:
            The `str` result produced by the operation.
        """
        return f"{self.name}@{self.major}"


@dataclass(frozen=True, slots=True)
class ServiceRequirement:
    """Represent the service requirement contract."""
    key: ServiceKey
    optional: bool = False


@dataclass(frozen=True, slots=True)
class ServiceRegistration:
    """Represent the service registration contract."""
    key: ServiceKey
    provider: str
    value: Any


class ServiceRegistry:
    """A startup-oriented registry with one provider per service key."""

    def __init__(self) -> None:
        """Initialize the service registry.

        Returns:
            None.
        """
        self._services: dict[ServiceKey, ServiceRegistration] = {}

    def provide(self, key: ServiceKey, value: Any, *, provider: str) -> None:
        """Implement the provide operation for the service registry.

        Args:
            key: Stable FIFO ordering key for the queued work.
            value: Value to validate, transform, or store.
            provider: The provider value used by the operation.

        Returns:
            None.
        """
        current = self._services.get(key)
        if current is not None:
            raise ServiceError(
                f"service {key} is already provided by {current.provider}; "
                f"{provider} cannot replace it"
            )
        self._services[key] = ServiceRegistration(key=key, provider=provider, value=value)

    def remove_provider(self, provider: str) -> None:
        """Remove provider.

        Args:
            provider: The provider value used by the operation.

        Returns:
            None.
        """
        for key in [key for key, item in self._services.items() if item.provider == provider]:
            del self._services[key]

    def remove(self, key: ServiceKey, *, provider: str | None = None) -> bool:
        """Remove one service when it is still owned by the expected provider."""

        current = self._services.get(key)
        if current is None or (provider is not None and current.provider != provider):
            return False
        del self._services[key]
        return True

    def require(self, key: ServiceKey) -> Any:
        """Return the service registry operation, failing when it is unavailable.

        Args:
            key: Stable FIFO ordering key for the queued work.

        Returns:
            The requested `Any` value.
        """
        try:
            return self._services[key].value
        except KeyError as exc:
            raise ServiceError(f"required service {key} is unavailable") from exc

    def get(self, key: ServiceKey, default: Any = None) -> Any:
        """Return the service registry operation.

        Args:
            key: Stable FIFO ordering key for the queued work.
            default: The default value used by the operation.

        Returns:
            The `Any` result produced by the operation.
        """
        item = self._services.get(key)
        return default if item is None else item.value

    def provider_for(self, key: ServiceKey) -> str | None:
        """Implement the provider for operation for the service registry.

        Args:
            key: Stable FIFO ordering key for the queued work.

        Returns:
            The `str | None` result produced by the operation.
        """
        item = self._services.get(key)
        return None if item is None else item.provider

    def snapshot(self) -> tuple[ServiceRegistration, ...]:
        """Return an immutable snapshot of the service registry state.

        Returns:
            The requested `tuple[ServiceRegistration, ...]` value.
        """
        return tuple(sorted(self._services.values(), key=lambda item: item.key))
