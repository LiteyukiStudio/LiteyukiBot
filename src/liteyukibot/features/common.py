"""Small host adapters shared by built-in Cordis features."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from typing import Any, Protocol, runtime_checkable

from liteyukibot_cordis import Scope, UnavailableProviderError

SERVICE_REGISTRY = "liteyukibot.service_registry"
LOGGER_PROVIDER = "liteyukibot.logger"


@runtime_checkable
class ServiceRegistryLike(Protocol):
    """Structural bridge to the host's service registry."""

    def provide(self, key: Hashable, value: object, *, provider: str) -> None:
        ...

    def remove_provider(self, provider: str) -> None:
        ...


class NullLogger:
    """Logger fallback for direct feature tests and minimal hosts."""

    def bind(self, **_fields: object) -> NullLogger:
        return self

    def debug(self, _message: str, *_args: object, **_kwargs: object) -> None:
        return None

    def info(self, _message: str, *_args: object, **_kwargs: object) -> None:
        return None

    def warning(self, _message: str, *_args: object, **_kwargs: object) -> None:
        return None

    def error(self, _message: str, *_args: object, **_kwargs: object) -> None:
        return None

    def exception(self, _message: str, *_args: object, **_kwargs: object) -> None:
        return None


class NullTranslator:
    """Use caller-provided fallback text when i18n is not composed."""

    def text(self, _key: str, fallback: str, **values: object) -> str:
        return fallback.format(**values)

    def text_for(self, _locale: str, _key: str, fallback: str = "", **values: object) -> str:
        return fallback.format(**values)


async def optional_use(scope: Scope, key: Hashable, default: Any) -> Any:
    """Resolve an optional ancestor provider without hiding provider failures."""
    try:
        return await scope.use(key)
    except UnavailableProviderError:
        return default


def config_mapping(config: Mapping[str, object] | None) -> dict[str, object]:
    """Copy a feature config while rejecting non-mapping inputs early."""
    if config is None:
        return {}
    if not isinstance(config, Mapping):
        raise TypeError("feature config must be an object")
    return dict(config)


async def publish_service(scope: Scope, key: Hashable, value: object) -> None:
    """Publish a service to Scope and optionally to the host registry."""
    scope.provide(key, lambda: value)
    registry = await optional_use(scope, SERVICE_REGISTRY, None)
    if registry is None:
        return
    if not isinstance(registry, ServiceRegistryLike):
        raise TypeError("feature service registry does not implement the kernel registry contract")
    registry.provide(key, value, provider=scope.plugin_id)

    def remove() -> None:
        registry.remove_provider(scope.plugin_id)

    scope.own(remove)


__all__ = [
    "LOGGER_PROVIDER",
    "SERVICE_REGISTRY",
    "NullLogger",
    "NullTranslator",
    "config_mapping",
    "optional_use",
    "publish_service",
]
