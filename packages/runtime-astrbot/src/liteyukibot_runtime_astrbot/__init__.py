"""AstrBot platform gateway for LiteyukiBot's standalone broker."""

from __future__ import annotations

from liteyukibot.broker import BridgeDefinition, BridgeSupportGrade

from .host import launch


def bridge_definition() -> BridgeDefinition:
    """Describe the experimental AstrBot gateway without importing AstrBot eagerly.

    Returns:
        The `BridgeDefinition` result produced by the operation.
    """

    return BridgeDefinition(
        kind="astrbot",
        grade=BridgeSupportGrade.EXPERIMENTAL,
        distribution="liteyukibot-v7-runtime-astrbot",
        launch=launch,
    )


__all__ = ["bridge_definition", "launch"]
