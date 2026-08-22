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
    """Represent the legacy bot context contract."""
    config: dict[str, Any]
    restart_callback: RestartFunction
    callbacks: dict[str, list[LifecycleCallback]] = field(default_factory=dict)

    def add(self, stage: str, callback: LifecycleCallback) -> LifecycleCallback:
        """Add the legacy bot context operation.

        Args:
            stage: The stage value used by the operation.
            callback: Callback invoked by the operation.

        Returns:
            The `LifecycleCallback` result produced by the operation.

        Notes:
            Internal implementation detail for `_LegacyBotContext.add`. It delegates to `append`,
            `setdefault` while keeping intermediate state local to the owning operation.
        """
        self.callbacks.setdefault(stage, []).append(callback)
        return callback

    async def emit(self, stage: str, *args: object) -> None:
        """Implement the emit operation for the legacy bot context.

        Args:
            stage: The stage value used by the operation.
            *args: The args value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_LegacyBotContext.emit`. It delegates to `get`, `callback`,
            `isawaitable` while keeping intermediate state local to the owning operation.
        """
        for callback in tuple(self.callbacks.get(stage, ())):
            result = callback(*args)
            if inspect.isawaitable(result):
                await result


_context: _LegacyBotContext | None = None


class LiteyukiBot:
    """Reject nested v6 hosts while explaining the supported migration path."""

    def __init__(self, **_kwargs: object) -> None:
        """Initialize the liteyuki bot.

        Args:
            **_kwargs: The kwargs value used by the operation.

        Returns:
            None.
        """
        raise LegacyUnsupportedError(
            "LiteyukiBot v6 plugins run inside the v7 compatibility runtime; "
            "constructing a nested LiteyukiBot is unsupported"
        )


class LegacyBot:
    """Represent the legacy bot contract."""
    def __init__(self, context: _LegacyBotContext) -> None:
        """Initialize the legacy bot.

        Args:
            context: Runtime or authorization context for the operation.

        Returns:
            None.
        """
        self._context = context

    @property
    def config(self) -> dict[str, Any]:
        """Return the legacy bot's config.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        return self._context.config

    def restart_process(self, name: str | None = None) -> None:
        """Implement the restart process operation for the legacy bot.

        Args:
            name: Stable name used to identify the value.

        Returns:
            None.
        """
        self._context.restart_callback(name)

    def on_before_start(self, callback: LifespanFunction) -> LifespanFunction:
        """Implement the on before start operation for the legacy bot.

        Args:
            callback: Callback invoked by the operation.

        Returns:
            The `LifespanFunction` result produced by the operation.
        """
        return self._context.add("before_start", callback)

    def on_after_start(self, callback: LifespanFunction) -> LifespanFunction:
        """Implement the on after start operation for the legacy bot.

        Args:
            callback: Callback invoked by the operation.

        Returns:
            The `LifespanFunction` result produced by the operation.
        """
        return self._context.add("after_start", callback)

    def on_after_shutdown(self, callback: LifespanFunction) -> LifespanFunction:
        """Implement the on after shutdown operation for the legacy bot.

        Args:
            callback: Callback invoked by the operation.

        Returns:
            The `LifespanFunction` result produced by the operation.
        """
        return self._context.add("after_shutdown", callback)

    def on_before_process_shutdown(self, callback: ProcessLifespanFunction) -> ProcessLifespanFunction:
        """Implement the on before process shutdown operation for the legacy bot.

        Args:
            callback: Callback invoked by the operation.

        Returns:
            The `ProcessLifespanFunction` result produced by the operation.
        """
        return self._context.add("before_process_shutdown", callback)

    def on_before_process_restart(self, callback: ProcessLifespanFunction) -> ProcessLifespanFunction:
        """Implement the on before process restart operation for the legacy bot.

        Args:
            callback: Callback invoked by the operation.

        Returns:
            The `ProcessLifespanFunction` result produced by the operation.
        """
        return self._context.add("before_process_restart", callback)

    def on_after_restart(self, callback: LifespanFunction) -> LifespanFunction:
        """Implement the on after restart operation for the legacy bot.

        Args:
            callback: Callback invoked by the operation.

        Returns:
            The `LifespanFunction` result produced by the operation.
        """
        return self._context.add("after_restart", callback)


def get_bot() -> LegacyBot:
    """Return bot.

    Returns:
        The requested `LegacyBot` value.
    """
    if _context is None:
        raise RuntimeError("Liteyuki v6 compatibility runtime is not initialized")
    return LegacyBot(_context)


def get_config(key: str, default: Any = None) -> Any:
    """Return config.

    Args:
        key: Stable FIFO ordering key for the queued work.
        default: The default value used by the operation.

    Returns:
        The requested `Any` value.
    """
    return get_bot().config.get(key, default)


def get_config_with_compat(key: str, compat_keys: tuple[str, ...], default: Any = None) -> Any:
    """Return config with compat.

    Args:
        key: Stable FIFO ordering key for the queued work.
        compat_keys: The compat keys value used by the operation.
        default: The default value used by the operation.

    Returns:
        The requested `Any` value.
    """
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
    """Install runtime.

    Args:
        config: Validated configuration used by the operation.
        restart_callback: The restart callback value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_install_runtime`. It delegates to `_LegacyBotContext` while
        keeping intermediate state local to the owning operation.
    """
    global _context
    if _context is not None:
        raise RuntimeError("Liteyuki v6 compatibility runtime is already initialized")
    _context = _LegacyBotContext(dict(config), restart_callback)


async def _emit_lifecycle(stage: str, *args: object) -> None:
    """Implement the emit lifecycle operation for the component.

    Args:
        stage: The stage value used by the operation.
        *args: The args value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_emit_lifecycle`. It delegates to `emit` while keeping
        intermediate state local to the owning operation.
    """
    if _context is None:
        raise RuntimeError("Liteyuki v6 compatibility runtime is not initialized")
    await _context.emit(stage, *args)


def _reset_runtime() -> None:
    """Implement the reset runtime operation for the component.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_reset_runtime`. It performs the local state transition
        directly and is not a stable extension boundary.
    """
    global _context
    _context = None


__all__ = ["LiteyukiBot", "get_bot", "get_config", "get_config_with_compat"]
