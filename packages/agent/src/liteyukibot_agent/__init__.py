"""Experimental Agent and Agent sandbox Broker bridges."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from liteyukibot.bridge_contracts import BridgeDefinition, BridgeSupportGrade

from .host import launch, launch_sandbox


def bridge_definition() -> BridgeDefinition:
    """Implement the bridge definition operation for the component.

    Returns:
        The `BridgeDefinition` result produced by the operation.
    """
    return BridgeDefinition(
        kind="agent",
        grade=BridgeSupportGrade.EXPERIMENTAL,
        distribution="liteyukibot-v7-agent",
        launch=launch,
    )


def sandbox_bridge_definition() -> BridgeDefinition:
    """Implement the sandbox bridge definition operation for the component.

    Returns:
        The `BridgeDefinition` result produced by the operation.
    """
    return BridgeDefinition(
        kind="agent-sandbox",
        grade=BridgeSupportGrade.EXPERIMENTAL,
        distribution="liteyukibot-v7-agent",
        launch=launch_sandbox,
    )


try:
    __version__ = version("liteyukibot-v7-agent")
except PackageNotFoundError:
    __version__ = "0.1.0a9"


__all__ = ["__version__", "bridge_definition", "sandbox_bridge_definition"]
