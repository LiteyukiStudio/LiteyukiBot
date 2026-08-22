"""Native OneBot protocol adapters for LiteyukiBot's Python adapter host."""

from __future__ import annotations

from liteyukibot_runtime_adapter.contracts import AdapterPlugin

from liteyukibot.broker import BridgeSupportGrade

from .v11 import create_v11
from .v12 import create_v12


def onebot_v11_plugin() -> AdapterPlugin:
    """Return the separately discoverable OneBot v11 adapter contract.

    Returns:
        The `AdapterPlugin` result produced by the operation.
    """

    return AdapterPlugin(
        kind="onebot-v11",
        distribution="liteyukibot-v7-adapter-onebot",
        grade=BridgeSupportGrade.STABLE,
        create=create_v11,
    )


def onebot_v12_plugin() -> AdapterPlugin:
    """Return the separately discoverable OneBot v12 adapter contract.

    Returns:
        The `AdapterPlugin` result produced by the operation.
    """

    return AdapterPlugin(
        kind="onebot-v12",
        distribution="liteyukibot-v7-adapter-onebot",
        grade=BridgeSupportGrade.EXPERIMENTAL,
        create=create_v12,
    )


__all__ = ["onebot_v11_plugin", "onebot_v12_plugin"]
