"""Native Satori v1 adapter for the Liteyuki adapter host."""

from __future__ import annotations

from liteyukibot_runtime_adapter.contracts import AdapterPlugin

from liteyukibot.broker import BridgeSupportGrade

from .connection import create_satori


def satori_plugin() -> AdapterPlugin:
    return AdapterPlugin(
        kind="satori",
        distribution="liteyukibot-v7-adapter-satori",
        grade=BridgeSupportGrade.EXPERIMENTAL,
        create=create_satori,
    )


__all__ = ["satori_plugin"]
