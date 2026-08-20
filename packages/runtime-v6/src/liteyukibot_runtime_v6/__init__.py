"""LiteyukiBot's separately distributed v6 compatibility bridge."""

from __future__ import annotations

from collections.abc import Awaitable

from liteyukibot.broker import BridgeDefinition, BridgeSupportGrade
from liteyukibot.config import AppSettings


def bridge_definition() -> BridgeDefinition:
    return BridgeDefinition(
        kind="v6",
        grade=BridgeSupportGrade.EXPERIMENTAL,
        distribution="liteyukibot-v7-runtime-v6",
        launch=_launch,
    )


def _launch(settings: AppSettings, bridge_id: str, token: str) -> Awaitable[None]:
    from .host import launch

    return launch(settings, bridge_id, token)


__all__ = ["bridge_definition"]
