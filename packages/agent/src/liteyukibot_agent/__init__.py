"""Native OpenAI-compatible agent runtime for LiteyukiBot v7."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

from liteyukibot import PluginDefinition
from liteyukibot.runtime import RuntimePlugin

from .plugin import create_plugin


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="agent",
        command=(sys.executable, "-m", "liteyukibot_agent"),
        agent_harness="native",
    )


try:
    __version__ = version("liteyukibot-v7-agent")
except PackageNotFoundError:
    __version__ = "0.1.0a1"

plugin: PluginDefinition = create_plugin(__version__)

__all__ = ["__version__", "plugin", "runtime_plugin"]
