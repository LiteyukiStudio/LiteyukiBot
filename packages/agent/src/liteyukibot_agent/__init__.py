"""Native OpenAI-compatible agent runtime for LiteyukiBot v7."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

from liteyukibot import PluginDefinition
from liteyukibot.runtime import InitFieldKind, InitFieldSpec, RuntimeInitSpec, RuntimePlugin

from .plugin import create_plugin


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="agent",
        command=(sys.executable, "-m", "liteyukibot_agent"),
        agent_harness="native",
        init_spec=RuntimeInitSpec(
            default_id="agent",
            description="Native OpenAI-compatible agent runtime.",
            fields=(
                InitFieldSpec(
                    key="model",
                    label="Model",
                    kind=InitFieldKind.STRING,
                    required=True,
                    description="OpenAI-compatible model identifier.",
                ),
                InitFieldSpec(
                    key="base_url",
                    label="Base URL",
                    kind=InitFieldKind.STRING,
                    description="Optional OpenAI-compatible API endpoint.",
                ),
                InitFieldSpec(
                    key="api_key_secret",
                    label="API key",
                    kind=InitFieldKind.SECRET,
                    required=True,
                    description="Stored by the kernel vault in the next configuration layer.",
                    secret_environment="LITEYUKI_AGENT_API_KEY",
                ),
            ),
        ),
    )


try:
    __version__ = version("liteyukibot-v7-agent")
except PackageNotFoundError:
    __version__ = "0.1.0a1"

plugin: PluginDefinition = create_plugin(__version__)

__all__ = ["__version__", "plugin", "runtime_plugin"]
