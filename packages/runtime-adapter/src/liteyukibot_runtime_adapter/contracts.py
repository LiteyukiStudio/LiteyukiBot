"""Public contracts implemented by separately published Python adapter packages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from liteyukibot.bridge_contracts import BridgeSupportGrade
from liteyukibot.broker import MessageSendPayload
from liteyukibot.events import EventEnvelope
from liteyukibot.json_value import JsonValue

EventEmitter = Callable[[EventEnvelope], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AdapterContext:
    """Immutable identity and opaque configuration for one adapter instance."""

    bridge_id: str
    instance_id: str
    kind: str
    bot_id: str
    config: Mapping[str, JsonValue]


class AdapterConnection(Protocol):
    """One live platform connection; SDK objects never leave this process."""

    async def start(self, emit: EventEmitter) -> None:
        """Connect and return only after the adapter can accept message.send.

        Args:
            emit: The emit value used by the operation.

        Returns:
            None.
        """

    async def send_message(self, payload: MessageSendPayload) -> JsonValue:
        """Execute one portable message.send already routed to this bot ID.

        Args:
            payload: JSON-safe payload carried by the operation.

        Returns:
            The `JsonValue` result produced by the operation.
        """

    async def close(self) -> None:
        """Release platform connections and background tasks.

        Returns:
            None.
        """

    async def wait_failure(self) -> None:
        """Wait until an unrecoverable background connection failure occurs.

        Returns:
            None.
        """


AdapterFactory = Callable[[AdapterContext], Awaitable[AdapterConnection]]


@dataclass(frozen=True, slots=True)
class AdapterPlugin:
    """One installable platform or protocol adapter discovered by entry point."""

    kind: str
    distribution: str
    grade: BridgeSupportGrade
    create: AdapterFactory

    def __post_init__(self) -> None:
        """Validate and normalize the adapter plugin after initialization.

        Returns:
            None.
        """
        if not self.kind or self.kind != self.kind.strip():
            raise ValueError("adapter kind must be a non-empty trimmed string")
        if not self.distribution or self.distribution != self.distribution.strip():
            raise ValueError("adapter distribution must be a non-empty trimmed string")
        if not isinstance(self.grade, BridgeSupportGrade) or self.grade is BridgeSupportGrade.MIXED:
            raise ValueError("adapter grade must be stable or experimental")
        if not callable(self.create):
            raise TypeError("adapter factory must be callable")


__all__ = ["AdapterConnection", "AdapterContext", "AdapterFactory", "AdapterPlugin", "EventEmitter"]
