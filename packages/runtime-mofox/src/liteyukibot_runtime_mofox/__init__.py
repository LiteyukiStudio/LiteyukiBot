"""Headless Neo-MoFox compatibility bridge for LiteyukiBot v7."""

from __future__ import annotations

from collections.abc import Awaitable

from liteyukibot.broker import BridgeDefinition, BridgeSupportGrade
from liteyukibot.config import AppSettings


def bridge_definition() -> BridgeDefinition:
    return BridgeDefinition(
        kind="mofox",
        grade=BridgeSupportGrade.EXPERIMENTAL,
        distribution="liteyukibot-v7-runtime-mofox",
        launch=_launch,
    )


def _launch(settings: AppSettings, bridge_id: str, token: str) -> Awaitable[None]:
    from .host import launch

    return launch(settings, bridge_id, token)


__all__ = ["bridge_definition"]
