"""Kernel-owned contracts for separately distributed Agent bridge packages."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .events import EventEnvelope
from .services import ServiceKey

AGENT_HISTORY_SERVICE = ServiceKey("liteyukibot.agent_history", 1)

@runtime_checkable
class AgentHistoryService(Protocol):
    """Clear the requesting principal's history through the Agent bridge."""

    async def clear(self, event: EventEnvelope) -> int:
        """Clear the agent history service operation.

        Args:
            event: Event associated with the operation.

        Returns:
            The `int` result produced by the operation.
        """
        ...


__all__ = ["AGENT_HISTORY_SERVICE", "AgentHistoryService"]
