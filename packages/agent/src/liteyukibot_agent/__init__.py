"""Native OpenAI-compatible agent runtime for LiteyukiBot v7."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

from liteyukibot import PluginDefinition
from liteyukibot.resource_packs import ResourcePackDeclaration
from liteyukibot.runtime import InitFieldKind, InitFieldSpec, RuntimeInitSpec, RuntimePlugin

from .plugin import create_plugin


def runtime_plugin() -> RuntimePlugin:
    return RuntimePlugin(
        kind="agent",
        command=(sys.executable, "-m", "liteyukibot_agent"),
        agent_harness="native",
        resource_packs=(ResourcePackDeclaration("liteyukibot_agent"),),
        init_spec=RuntimeInitSpec(
            default_id="agent",
            description="Native OpenAI-compatible agent runtime.",
            fields=(
                InitFieldSpec(
                    key="model",
                    label="Model",
                    label_key="agent.init.model",
                    kind=InitFieldKind.STRING,
                    required=True,
                    description="OpenAI-compatible model identifier.",
                ),
                InitFieldSpec(
                    key="base_url",
                    label="Base URL",
                    label_key="agent.init.base_url",
                    kind=InitFieldKind.STRING,
                    description="Optional OpenAI-compatible API endpoint.",
                ),
                InitFieldSpec(
                    key="model_timeout_seconds",
                    label="Model timeout seconds",
                    kind=InitFieldKind.INTEGER,
                    default=60,
                    description="Maximum duration for one model request.",
                ),
                InitFieldSpec(
                    key="event_timeout_seconds",
                    label="Event timeout seconds",
                    kind=InitFieldKind.INTEGER,
                    default=120,
                    description="Maximum total duration for one delivered event.",
                ),
                InitFieldSpec(
                    key="max_tool_rounds",
                    label="Maximum tool rounds",
                    kind=InitFieldKind.INTEGER,
                    default=4,
                    description="Maximum model-to-tool iteration rounds per event.",
                ),
                InitFieldSpec(
                    key="history_limit",
                    label="History messages",
                    kind=InitFieldKind.INTEGER,
                    default=40,
                    description="Maximum stored conversation messages sent to a model request.",
                ),
                InitFieldSpec(
                    key="max_concurrent_events",
                    label="Concurrent events",
                    kind=InitFieldKind.INTEGER,
                    default=16,
                    description="Maximum in-flight events handled by this agent runtime.",
                ),
                InitFieldSpec(
                    key="api_key_secret",
                    label="API key",
                    label_key="agent.init.api_key",
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
    __version__ = "0.1.0a7"

plugin: PluginDefinition = create_plugin(__version__)

__all__ = ["__version__", "plugin", "runtime_plugin"]
