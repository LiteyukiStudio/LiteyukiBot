"""Application-owned Yukilog configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from yukilog import (
    ConsoleSink,
    FileSink,
    JsonSink,
    Logger,
    LoggingConfig,
    configure,
    get_logger,
    intercept_stdlib_logging,
    shutdown,
)

from .config import LoggingSettings
from .config.redaction import redact_config


def configure_logging(settings: LoggingSettings) -> Logger:
    """Install the sinks selected by the immutable application settings.

    Args:
        settings: Validated application settings.

    Returns:
        The `Logger` result produced by the operation.
    """

    console = ConsoleSink(level=settings.level) if settings.console else None
    json_sink = JsonSink(level=settings.level) if settings.json_lines else None
    files: tuple[FileSink, ...] = ()
    if settings.file is not None:
        files = (
            FileSink(
                path=settings.file,
                level=settings.level,
                rotation=settings.rotation,
                retention=settings.retention,
            ),
        )
    configure(LoggingConfig(console=console, json=json_sink, files=files))
    intercept_stdlib_logging()
    return get_logger(component="core")


def shutdown_logging() -> None:
    """Implement the shutdown logging operation for the component.

    Returns:
        None.
    """
    shutdown()


def log_payload(
    logger: Logger,
    settings: LoggingSettings,
    *,
    operation: str,
    payload: Mapping[str, Any],
    runtime_id: str | None = None,
) -> None:
    """Emit a redacted structured payload only when full payload logging is selected.

    Args:
        logger: Structured logger used for diagnostics.
        settings: Validated application settings.
        operation: The operation value used by the operation.
        payload: JSON-safe payload carried by the operation.
        runtime_id: Stable runtime identifier.

    Returns:
        None.
    """

    if settings.payload_mode != "full":
        return
    logger.bind(
        component="payload",
        operation=operation,
        runtime=runtime_id,
        payload=redact_config(payload),
    ).debug("payload recorded")


__all__ = [
    "Logger",
    "configure_logging",
    "get_logger",
    "log_payload",
    "shutdown_logging",
]
