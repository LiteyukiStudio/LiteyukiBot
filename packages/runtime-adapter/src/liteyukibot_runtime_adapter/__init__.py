"""LiteyukiBot's separately distributed Python platform adapter host."""

from __future__ import annotations

import sys

from liteyukibot.runtime import RuntimeInitSpec, RuntimePlugin

from .facets import AdapterFacetInstaller


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="adapter",
        command=(sys.executable, "-m", "liteyukibot_runtime_adapter"),
        distribution="liteyukibot-v7-runtime-adapter",
        facet_installer=AdapterFacetInstaller(),
        init_spec=RuntimeInitSpec(
            default_id="platform",
            description="Python platform adapter host. Configure adapter instances in runtime options.",
            default_options={"adapters": {}},
        ),
    )


__all__ = ["runtime_plugin"]
