"""Versioned project configuration template owned by the kernel package."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from tomli_w import dumps

CONFIG_VERSION = 6


def render_config_template(
    *,
    data_dir: str = "data",
    cache_dir: str = "cache",
    logging_level: str = "INFO",
    logging_console: bool = True,
    logging_json_lines: bool = False,
    payload_mode: str = "metadata",
    payload_exclude_runtimes: Iterable[str] = (),
    locale: str = "auto",
    plugins: Iterable[str] = (),
    plugin_config: dict[str, dict[str, Any]] | None = None,
    cordis_plugins: Iterable[str] = (),
    cordis_config: dict[str, Any] | None = None,
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
            "console": logging_console,
            "json_lines": logging_json_lines,
            "payload_mode": payload_mode,
            "payload_exclude_runtimes": list(payload_exclude_runtimes),
        },
        "i18n": {"locale": locale},
        "plugins": {
            "enabled": list(plugins),
            "local_modules": [],
            "config": plugin_config or {},
        },
        "cordis": {
            "enabled": list(cordis_plugins),
            "config": cordis_config or {},
            "access": {},
        },
        "http": {"enabled": False, "host": "127.0.0.1", "port": 20216},
        "daemon": {
            "auto_restart": False,
            "manage_broker": True,
            "manage_bridges": True,
            "restart_limit": 5,
            "restart_window_seconds": 60.0,
            "restart_backoff_initial_seconds": 0.5,
            "restart_backoff_max_seconds": 10.0,
            "startup_timeout_seconds": 30.0,
            "stop_timeout_seconds": 10.0,
            "drain_timeout_seconds": 30.0,
            "health_timeout_seconds": 30.0,
        },
        "lyip": {
            "default_backend": "auto",
            "capacity_profile": "balanced",
            "terminal_capacity": 16384,
            "terminal_ttl_seconds": 3600,
            "dev_summary_ttl_seconds": 900,
            "zmq_large_payload_fallback": False,
            "links": {},
        },
        "broker": {
            "endpoint": "tcp://127.0.0.1:20217",
            "generation": 1,
            "active_capacity": 1024,
            "terminal_capacity": 16384,
            "terminal_ttl_seconds": 3600,
            "delivery_timeout_seconds": 30,
            "bridges": {},
        },
        "webui": {
            "mode": "on_demand",
            "port": 0,
            "idle_shutdown_seconds": 300,
            "ticket_ttl_seconds": 60,
            "session_idle_seconds": 1800,
            "session_max_seconds": 28800,
        },
        "development": {
            "enabled": False,
            "allow_drills": False,
            "watch_auto_restart": False,
            "watch_debounce_seconds": 0.75,
        },
    }
    return "# LiteyukiBot configuration schema. Do not edit config_version manually.\n" + dumps(document)
