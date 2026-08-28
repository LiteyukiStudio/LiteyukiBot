"""Small host adapters shared by built-in Cordis features."""

from __future__ import annotations

import asyncio
import threading
import weakref
from collections.abc import Callable, Hashable, Mapping
from typing import Any, Protocol, runtime_checkable

from liteyukibot_cordis import Scope, UnavailableProviderError

SERVICE_REGISTRY = "liteyukibot.service_registry"
LOGGER_PROVIDER = "liteyukibot.logger"
_BLOCKING_OPERATION_CAPACITY = 32
_blocking_slots: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = weakref.WeakKeyDictionary()
_blocking_slots_lock = threading.Lock()


def _blocking_slot_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    with _blocking_slots_lock:
        slots = _blocking_slots.get(loop)
        if slots is None:
            slots = asyncio.Semaphore(_BLOCKING_OPERATION_CAPACITY)
            _blocking_slots[loop] = slots
        return slots


async def run_blocking[ThreadResult](operation: Callable[[], ThreadResult]) -> ThreadResult:
    """Run one bounded synchronous converter while preserving cancellation as a FIFO barrier."""

    async def run() -> ThreadResult:
        async with _blocking_slot_semaphore():
            return await asyncio.to_thread(operation)

    task = asyncio.create_task(run(), name="liteyukibot-blocking-feature-operation")
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await asyncio.shield(task)
        except BaseException:
            pass
        raise


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
    exact_remove = getattr(registry, "remove", None)
    provider = scope.plugin_id if callable(exact_remove) else f"{scope.plugin_id}:{scope.id}"
    registry.provide(key, value, provider=provider)

    async def remove() -> None:
        if callable(exact_remove):
            exact_remove(key, provider=provider)
        else:
            registry.remove_provider(provider)

    scope.own(remove)


__all__ = [
    "LOGGER_PROVIDER",
    "SERVICE_REGISTRY",
    "NullLogger",
    "NullTranslator",
    "config_mapping",
    "optional_use",
    "publish_service",
    "run_blocking",
]
