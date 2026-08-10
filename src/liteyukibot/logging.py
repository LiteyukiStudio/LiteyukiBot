"""Application-owned Yukilog configuration."""

from __future__ import annotations

import os

from yukilog import (
    ConsoleSink,
    FileSink,
    JsonSink,
    Logger,
    LoggingConfig,
    configure,
    configure_child_runtime,
    get_logger,
    intercept_stdlib_logging,
    shutdown,
)

from .config import LoggingSettings


def configure_logging(settings: LoggingSettings) -> Logger:
    """Install the sinks selected by the immutable application settings."""

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
    shutdown()


def configure_runtime_child_logging() -> Logger:
    """Configure a child host from supervisor-provided logging environment."""

    configure_child_runtime(level=os.environ.get("LITEYUKI_RUNTIME_LOG_LEVEL", "INFO"))
    intercept_stdlib_logging()
    return get_logger(
        component=os.environ.get("LITEYUKI_RUNTIME_KIND", "runtime"),
        runtime=os.environ.get("LITEYUKI_RUNTIME_ID"),
    )


__all__ = [
    "Logger",
    "configure_logging",
    "configure_runtime_child_logging",
    "get_logger",
    "shutdown_logging",
]
