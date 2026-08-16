"""Discovery and narrow native planning interface for the Cordis runtime."""

from __future__ import annotations

from liteyukibot.runtime import RuntimeInitSpec, RuntimePlugin

from ._native import builtin_catchers_json, plan_actions_json, validate_config_json
from .binary import cordis_binary_command


def runtime_plugin() -> RuntimePlugin:
    """Return the Cordis child runtime without falling back to a Python host."""

    return RuntimePlugin(
        kind="cordis",
        command=cordis_binary_command(),
        default_event_route_messages_only=True,
        distribution="liteyukibot-v7-runtime-cordis",
        init_spec=RuntimeInitSpec(
            default_id="cordis",
            description="First-party closed Cordis catcher runtime.",
            default_options={"enabled": ("core.greeting", "core.help", "core.status")},
        ),
    )


__all__ = [
    "builtin_catchers_json",
    "plan_actions_json",
    "runtime_plugin",
    "validate_config_json",
]
