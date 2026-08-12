"""Native OneBot protocol adapters for LiteyukiBot's Python adapter host."""

from __future__ import annotations

from liteyukibot_runtime_adapter.contracts import AdapterPlugin

from .v11 import create_v11


def onebot_v11_plugin() -> AdapterPlugin:
    """Return the separately discoverable OneBot v11 adapter contract."""

    return AdapterPlugin("onebot-v11", create_v11)


__all__ = ["onebot_v11_plugin"]
