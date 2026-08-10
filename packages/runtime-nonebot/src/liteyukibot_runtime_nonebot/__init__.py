"""LiteyukiBot's separately distributed NoneBot runtime host."""

from __future__ import annotations

import sys

from liteyukibot.runtime import RuntimePlugin


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="nonebot",
        command=(sys.executable, "-m", "liteyukibot_runtime_nonebot"),
    )


__all__ = ["runtime_plugin"]
