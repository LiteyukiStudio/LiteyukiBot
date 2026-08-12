"""Headless AstrBot agent runtime for LiteyukiBot v7."""

from __future__ import annotations

import sys

from liteyukibot.resource_packs import ResourcePackDeclaration
from liteyukibot.runtime import InitFieldKind, InitFieldSpec, RuntimeInitSpec, RuntimePlugin

from .facets import AstrBotFacetInstaller


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="astrbot",
        command=(sys.executable, "-m", "liteyukibot_runtime_astrbot"),
        agent_harness="astrbot",
        distribution="liteyukibot-v7-runtime-astrbot",
        resource_packs=(ResourcePackDeclaration("liteyukibot_runtime_astrbot"),),
        facet_installer=AstrBotFacetInstaller(),
        init_spec=RuntimeInitSpec(
            default_id="astrbot",
            description="Headless AstrBot agent host with managed plugin projections.",
            default_options={"projection_mode": "copy"},
            fields=(
                InitFieldSpec(
                    "projection_mode",
                    "Managed plugin projection mode",
                    InitFieldKind.STRING,
                    label_key="runtime.astrbot.init.projection_mode",
                    default="copy",
                    choices=("copy", "symlink"),
                    description="copy works without link privileges; symlink requires platform support.",
                ),
            ),
        ),
    )


__all__ = ["runtime_plugin"]
