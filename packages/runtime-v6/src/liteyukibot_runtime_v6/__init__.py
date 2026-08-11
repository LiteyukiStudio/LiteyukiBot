"""LiteyukiBot's separately distributed v6 compatibility runtime."""

from __future__ import annotations

import sys

from liteyukibot.runtime import RuntimePlugin


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="v6",
        command=(sys.executable, "-m", "liteyukibot_runtime_v6"),
        default_event_route_messages_only=True,
    )


__all__ = ["runtime_plugin"]
