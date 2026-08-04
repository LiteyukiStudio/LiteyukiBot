"""Supported LiteyukiBot v6 application facade."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from liteyukibot.exceptions import LegacyUnsupportedError

type LifespanFunction = Callable[[], Any]
type ProcessLifespanFunction = Callable[[str], Any]
type RestartFunction = Callable[[str | None], None]
type LifecycleCallback = Callable[..., Any]


@dataclass(slots=True)
class _LegacyBotContext:
    config: dict[str, Any]
    restart_callback: RestartFunction
    callbacks: dict[str, list[LifecycleCallback]] = field(default_factory=dict)

    def add(self, stage: str, callback: LifecycleCallback) -> LifecycleCallback:
        self.callbacks.setdefault(stage, []).append(callback)
        return callback

    async def emit(self, stage: str, *args: object) -> None:
        for callback in tuple(self.callbacks.get(stage, ())):
            result = callback(*args)
            if inspect.isawaitable(result):
                await result


_context: _LegacyBotContext | None = None


class LiteyukiBot:
    """Reject nested v6 hosts while explaining the supported migration path."""

    def __init__(self, **_kwargs: object) -> None:
        raise LegacyUnsupportedError(
            "LiteyukiBot v6 plugins run inside the v7 compatibility runtime; "
            "constructing a nested LiteyukiBot is unsupported"
        )


class LegacyBot:
    def __init__(self, context: _LegacyBotContext) -> None:
        self._context = context

    @property
    def config(self) -> dict[str, Any]:
        return self._context.config

    def restart_process(self, name: str | None = None) -> None:
        self._context.restart_callback(name)

    def on_before_start(self, callback: LifespanFunction) -> LifespanFunction:
        return self._context.add("before_start", callback)

    def on_after_start(self, callback: LifespanFunction) -> LifespanFunction:
        return self._context.add("after_start", callback)

    def on_after_shutdown(self, callback: LifespanFunction) -> LifespanFunction:
        return self._context.add("after_shutdown", callback)

    def on_before_process_shutdown(
        self, callback: ProcessLifespanFunction
    ) -> ProcessLifespanFunction:
        return self._context.add("before_process_shutdown", callback)

    def on_before_process_restart(
        self, callback: ProcessLifespanFunction
    ) -> ProcessLifespanFunction:
        return self._context.add("before_process_restart", callback)

    def on_after_restart(self, callback: LifespanFunction) -> LifespanFunction:
        return self._context.add("after_restart", callback)


def get_bot() -> LegacyBot:
    if _context is None:
        raise RuntimeError("Liteyuki v6 compatibility runtime is not initialized")
    return LegacyBot(_context)


def get_config(key: str, default: Any = None) -> Any:
    return get_bot().config.get(key, default)


def get_config_with_compat(key: str, compat_keys: tuple[str, ...], default: Any = None) -> Any:
    config = get_bot().config
    if key in config:
        return config[key]
    for compat_key in compat_keys:
        if compat_key in config:
            from liteyuki.log import logger

            logger.warning('Config key "{}" is deprecated; use "{}"', compat_key, key)
            return config[compat_key]
    return default


def _install_runtime(config: Mapping[str, Any], restart_callback: RestartFunction) -> None:
    global _context
    if _context is not None:
        raise RuntimeError("Liteyuki v6 compatibility runtime is already initialized")
    _context = _LegacyBotContext(dict(config), restart_callback)


async def _emit_lifecycle(stage: str, *args: object) -> None:
    if _context is None:
        raise RuntimeError("Liteyuki v6 compatibility runtime is not initialized")
    await _context.emit(stage, *args)


def _reset_runtime() -> None:
    global _context
    _context = None


__all__ = ["LiteyukiBot", "get_bot", "get_config", "get_config_with_compat"]
