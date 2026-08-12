"""Headless Neo-MoFox agent runtime for LiteyukiBot v7."""

from __future__ import annotations

import sys

from liteyukibot.resource_packs import ResourcePackDeclaration
from liteyukibot.runtime import InitFieldKind, InitFieldSpec, RuntimeInitSpec, RuntimePlugin

from .facets import MoFoxFacetInstaller


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="mofox",
        command=(sys.executable, "-m", "liteyukibot_runtime_mofox"),
        agent_harness="mofox",
        distribution="liteyukibot-v7-runtime-mofox",
        resource_packs=(ResourcePackDeclaration("liteyukibot_runtime_mofox"),),
        facet_installer=MoFoxFacetInstaller(),
        init_spec=RuntimeInitSpec(
            default_id="mofox",
            description="Headless Neo-MoFox agent host with managed plugin projections.",
            default_options={"projection_mode": "copy"},
            fields=(
                InitFieldSpec(
                    "projection_mode",
                    "Managed plugin projection mode",
                    InitFieldKind.STRING,
                    label_key="runtime.mofox.init.projection_mode",
                    default="copy",
                    choices=("copy", "symlink"),
                    description="copy works without link privileges; symlink requires platform support.",
                ),
            ),
        ),
    )


__all__ = ["runtime_plugin"]
