"""Headless Neo-MoFox agent runtime for LiteyukiBot v7."""

from __future__ import annotations

import sys

from liteyukibot.runtime import RuntimePlugin


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="mofox",
        command=(sys.executable, "-m", "liteyukibot_runtime_mofox"),
        agent_harness="mofox",
    )


__all__ = ["runtime_plugin"]
