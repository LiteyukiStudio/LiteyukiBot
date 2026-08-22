"""Headless Neo-MoFox compatibility bridge for LiteyukiBot v7."""

from __future__ import annotations

from collections.abc import Awaitable

from liteyukibot.broker import BridgeDefinition, BridgeSupportGrade
from liteyukibot.config import AppSettings


def bridge_definition() -> BridgeDefinition:
    """Implement the bridge definition operation for the component.

    Returns:
        The `BridgeDefinition` result produced by the operation.
    """
    return BridgeDefinition(
        kind="mofox",
        grade=BridgeSupportGrade.EXPERIMENTAL,
        distribution="liteyukibot-v7-runtime-mofox",
        launch=_launch,
    )


def _launch(settings: AppSettings, bridge_id: str, token: str) -> Awaitable[None]:
    """Launch the component operation.

    Args:
        settings: Validated application settings.
        bridge_id: Stable identifier for the bridge.
        token: Authentication token presented at the boundary.

    Returns:
        The `Awaitable[None]` result produced by the operation.

    Notes:
        Internal implementation detail for `_launch`. It delegates to `launch` while keeping
        intermediate state local to the owning operation.
    """
    from .host import launch

    return launch(settings, bridge_id, token)


__all__ = ["bridge_definition"]
