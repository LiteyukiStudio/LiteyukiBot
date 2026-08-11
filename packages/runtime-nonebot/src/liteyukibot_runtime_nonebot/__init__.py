"""LiteyukiBot's separately distributed NoneBot runtime host."""

from __future__ import annotations

import sys

from liteyukibot.runtime import RuntimeInitSpec, RuntimePlugin


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="nonebot",
        command=(sys.executable, "-m", "liteyukibot_runtime_nonebot"),
        init_spec=RuntimeInitSpec(
            default_id="nonebot",
            description="NoneBot child host. Configure framework plugins and adapters in its runtime options.",
            default_options={
                "plugins": (),
                "plugin_dirs": (),
                "adapters": ("nonebot.adapters.onebot.v11:Adapter",),
                "config": {"driver": "~fastapi"},
            },
        ),
    )


__all__ = ["runtime_plugin"]
