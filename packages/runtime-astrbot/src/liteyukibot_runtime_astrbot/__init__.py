"""Headless AstrBot agent runtime for LiteyukiBot v7."""

from __future__ import annotations

import sys

from liteyukibot.runtime import RuntimeInitSpec, RuntimePlugin


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="astrbot",
        command=(sys.executable, "-m", "liteyukibot_runtime_astrbot"),
        agent_harness="astrbot",
        init_spec=RuntimeInitSpec(
            default_id="astrbot",
            description="Headless AstrBot agent host; AstrBot plugins remain runtime-owned.",
        ),
    )


__all__ = ["runtime_plugin"]
