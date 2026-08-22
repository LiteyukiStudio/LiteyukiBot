"""LiteyukiBot's separately distributed NoneBot broker bridge."""

from liteyukibot.broker import BridgeDefinition, BridgeSupportGrade

from .host import launch


def bridge_definition() -> BridgeDefinition:
    """Describe the stable NoneBot bridge without importing NoneBot eagerly.

    Returns:
        The `BridgeDefinition` result produced by the operation.
    """

    return BridgeDefinition(
        kind="nonebot",
        grade=BridgeSupportGrade.STABLE,
        distribution="liteyukibot-v7-runtime-nonebot",
        launch=launch,
    )


__all__ = ["bridge_definition", "launch"]
