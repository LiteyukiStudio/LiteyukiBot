"""Headless AstrBot agent runtime for LiteyukiBot v7."""

from __future__ import annotations

import sys

from liteyukibot.runtime import RuntimePlugin


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="astrbot",
        command=(sys.executable, "-m", "liteyukibot_runtime_astrbot"),
        agent_harness="astrbot",
    )


__all__ = ["runtime_plugin"]
