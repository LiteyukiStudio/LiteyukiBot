"""Application-owned Yukilog configuration."""

from __future__ import annotations

import hashlib
import threading
from collections import deque
from collections.abc import Mapping
from typing import Any

from loguru import logger as _loguru_logger
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

_WEBUI_LOG_LIMIT = 1000
_WEBUI_LOG_MESSAGE_LIMIT = 4096
_webui_logs: deque[dict[str, object]] = deque(maxlen=_WEBUI_LOG_LIMIT)
_webui_logs_lock = threading.RLock()
_webui_log_sink_id: int | None = None


def _capture_webui_log(message: Any) -> None:
    """Handle `_capture_webui_log`.

    Args:
        message: Input accepted by this callable.

    Returns:
        Result produced by this callable.

    Notes:
        This helper remains internal to its owning implementation.
    """
    record = message.record
    extra = dict(record.get("extra", {}))
    component = str(extra.pop("component", "core"))
    context = redact_config({key: value for key, value in extra.items() if not key.startswith("_")})
    timestamp = record["time"].astimezone().isoformat()
    identity = hashlib.sha256(f"{timestamp}:{record['level'].name}:{record['message']}".encode()).hexdigest()[:24]
    item = {
        "id": identity,
        "at": timestamp,
        "level": str(record["level"].name).lower(),
        "component": component if component in {"core", "daemon", "runtime", "plugin", "broker"} else "core",
        "message": str(record["message"])[:_WEBUI_LOG_MESSAGE_LIMIT],
        "context": context if isinstance(context, Mapping) else {},
    }
    with _webui_logs_lock:
        _webui_logs.append(item)


def get_webui_logs(
    *, cursor: str | None, limit: int, level: str | None, component: str | None, query: str
) -> dict[str, object]:
    """Handle `get_webui_logs`.

    Args:
        cursor: Input accepted by this callable.
        limit: Input accepted by this callable.
        level: Input accepted by this callable.
        component: Input accepted by this callable.
        query: Input accepted by this callable.

    Returns:
        Result produced by this callable.
    """
    with _webui_logs_lock:
        items = list(_webui_logs)
    if level is not None:
        items = [item for item in items if item["level"] == level]
    if component is not None:
        items = [item for item in items if item["component"] == component]
    if query:
        items = [item for item in items if query.casefold() in str(item["message"]).casefold()]
    offset = int(cursor or "0")
    page = items[offset : offset + limit]
    return {
        "items": page,
        "next_cursor": str(offset + limit) if offset + limit < len(items) else None,
        "total_retained": len(items),
        "diagnostics": [],
    }


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
    global _webui_log_sink_id
    if _webui_log_sink_id is not None:
        _loguru_logger.remove(_webui_log_sink_id)
    _webui_log_sink_id = _loguru_logger.add(_capture_webui_log, level="DEBUG")
    intercept_stdlib_logging()
    return get_logger(component="core")


def shutdown_logging() -> None:
    """Implement the shutdown logging operation for the component.

    Returns:
        None.
    """
    global _webui_log_sink_id
    if _webui_log_sink_id is not None:
        _loguru_logger.remove(_webui_log_sink_id)
        _webui_log_sink_id = None
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
