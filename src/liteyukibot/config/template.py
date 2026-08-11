"""Versioned project configuration template owned by the kernel package."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from tomli_w import dumps

CONFIG_VERSION = 1


def render_config_template(
    *,
    data_dir: str = "data",
    cache_dir: str = "cache",
    logging_level: str = "INFO",
    payload_mode: str = "metadata",
    payload_exclude_runtimes: Iterable[str] = (),
    plugins: Iterable[str] = (),
    plugin_config: dict[str, dict[str, Any]] | None = None,
    runtimes: dict[str, dict[str, Any]] | None = None,
    runtime_event_routes: Iterable[dict[str, Any]] = (),
) -> str:
    document = {
        "config_version": CONFIG_VERSION,
        "core": {
            "data_dir": data_dir,
            "cache_dir": cache_dir,
            "queue_capacity": 1024,
            "enqueue_timeout_seconds": 1.0,
            "handler_timeout_seconds": 30.0,
            "max_concurrent_events": 100,
        },
        "logging": {
            "level": logging_level,
            "console": True,
            "json_lines": False,
            "payload_mode": payload_mode,
            "payload_exclude_runtimes": list(payload_exclude_runtimes),
        },
        "plugins": {
            "enabled": list(plugins),
            "local_modules": [],
            "config": plugin_config or {},
        },
        "http": {"enabled": False, "host": "127.0.0.1", "port": 20216},
        "runtimes": runtimes or {},
        "runtime_event_routes": list(runtime_event_routes),
    }
    return "# LiteyukiBot configuration schema. Do not edit config_version manually.\n" + dumps(document)
