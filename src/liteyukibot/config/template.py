"""Versioned project configuration template owned by the local application."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from tomli_w import dumps

CONFIG_VERSION = 7


def render_config_template(
    *,
    data_dir: str = "data",
    cache_dir: str = "cache",
    logging_level: str = "INFO",
    logging_console: bool = True,
    logging_json_lines: bool = False,
    payload_mode: str = "metadata",
    locale: str = "auto",
    cordis_plugins: Iterable[str] = (),
    cordis_config: dict[str, Any] | None = None,
    permissions: dict[str, Any] | None = None,
    commands: dict[str, Any] | None = None,
    resources: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    essentials: dict[str, Any] | None = None,
    onebot: dict[str, Any] | None = None,
) -> str:
    """Render the minimal v7 configuration document."""
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
        },
        "i18n": {"locale": locale},
        "cordis": {
            "enabled": list(cordis_plugins),
            "config": cordis_config or {},
        },
        "permissions": {
            "grants": [],
            "roles": {},
            **(permissions or {}),
        },
        "commands": {"prefixes": ["/"], **(commands or {})},
        "resources": {**(resources or {})},
        "profile": {**(profile or {})},
        "essentials": {"language": "zh-CN", **(essentials or {})},
        "onebot": {
            "v11": {"accounts": {}},
            **(onebot or {}),
        },
    }
    return "# LiteyukiBot configuration schema. Do not edit config_version manually.\n" + dumps(document)
