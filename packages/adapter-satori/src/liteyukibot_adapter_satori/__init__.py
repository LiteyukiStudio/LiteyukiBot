"""Native Satori v1 adapter for the Liteyuki adapter host."""

from __future__ import annotations

from liteyukibot_runtime_adapter.contracts import AdapterPlugin

from liteyukibot.broker import BridgeSupportGrade

from .connection import create_satori


def satori_plugin() -> AdapterPlugin:
    """Implement the satori plugin operation for the component.

    Returns:
        The `AdapterPlugin` result produced by the operation.
    """
    return AdapterPlugin(
        kind="satori",
        distribution="liteyukibot-v7-adapter-satori",
        grade=BridgeSupportGrade.EXPERIMENTAL,
        create=create_satori,
    )


__all__ = ["satori_plugin"]
