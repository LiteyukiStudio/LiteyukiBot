"""Native Satori v1 adapter for the Liteyuki adapter host."""

from __future__ import annotations

from liteyukibot_runtime_adapter.contracts import AdapterPlugin

from .connection import create_satori


def satori_plugin() -> AdapterPlugin:
    return AdapterPlugin("satori", create_satori)


__all__ = ["satori_plugin"]
