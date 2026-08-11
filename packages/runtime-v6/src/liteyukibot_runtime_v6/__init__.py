"""LiteyukiBot's separately distributed v6 compatibility runtime."""

from __future__ import annotations

import sys

from liteyukibot.runtime import RuntimeInitSpec, RuntimePlugin


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="v6",
        command=(sys.executable, "-m", "liteyukibot_runtime_v6"),
        default_event_route_messages_only=True,
        init_spec=RuntimeInitSpec(
            default_id="legacy",
            description="Bounded LiteyukiBot v6 compatibility host.",
            default_options={"plugins": (), "plugin_dirs": ("plugins",), "config": {"nickname": ("Liteyuki",)}},
        ),
    )


__all__ = ["runtime_plugin"]
