"""Versioned project configuration template owned by the kernel package."""

from __future__ import annotations

import json
from collections.abc import Iterable

CONFIG_VERSION = 1


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def render_config_template(
    *,
    data_dir: str = "data",
    cache_dir: str = "cache",
    logging_level: str = "INFO",
    payload_mode: str = "metadata",
    payload_exclude_runtimes: Iterable[str] = (),
) -> str:
    excluded = ", ".join(_toml_string(item) for item in payload_exclude_runtimes)
    return f'''# LiteyukiBot configuration schema. Do not edit config_version manually.
config_version = {CONFIG_VERSION}

[core]
data_dir = {_toml_string(data_dir)}
cache_dir = {_toml_string(cache_dir)}
queue_capacity = 1024
enqueue_timeout_seconds = 1.0
handler_timeout_seconds = 30.0
max_concurrent_events = 100

[logging]
level = {_toml_string(logging_level)}
console = true
json_lines = false
# Full payload logs can contain message content and identifiers. Keep metadata unless debugging.
payload_mode = {_toml_string(payload_mode)}
payload_exclude_runtimes = [{excluded}]

[plugins]
enabled = []
local_modules = []

[plugins.config."liteyukibot.permissions"]
grants = []

[plugins.config."liteyukibot.permissions".roles]
operator = ["liteyukibot.status.read"]

[plugins.config."liteyukibot.commands"]
prefixes = ["/"]

[plugins.config."liteyukibot.essentials"]
language = "zh-CN"

[http]
enabled = false
host = "127.0.0.1"
port = 20216

[runtimes.nonebot]
# Install with: uv add "liteyukibot-v7-runtime-nonebot[onebot]"
kind = "nonebot"
enabled = false
heartbeat_interval_seconds = 10.0
stale_after_seconds = 30.0
max_inbound_events = 100

[runtimes.nonebot.options]
plugins = []
plugin_dirs = []
adapters = ["nonebot.adapters.onebot.v11:Adapter"]

[runtimes.nonebot.options.config]
driver = "~fastapi"

[runtimes.legacy]
# Install with: uv add "liteyukibot-v7-runtime-v6"
kind = "v6"
enabled = false

[runtimes.legacy.options]
plugins = []
plugin_dirs = ["plugins"]

[runtimes.legacy.options.config]
nickname = ["Liteyuki"]
'''
