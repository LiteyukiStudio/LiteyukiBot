"""LiteyukiBot's separately distributed Python adapter Broker bridge."""

from __future__ import annotations

from liteyukibot.broker import BridgeDefinition, BridgeSupportGrade

from .host import launch


def bridge_definition() -> BridgeDefinition:
    """Describe the mixed-grade adapter bridge without importing drivers eagerly.

    Returns:
        The `BridgeDefinition` result produced by the operation.
    """

    return BridgeDefinition(
        kind="adapter",
        grade=BridgeSupportGrade.MIXED,
        distribution="liteyukibot-v7-runtime-adapter",
        launch=launch,
    )


__all__ = ["bridge_definition", "launch"]
