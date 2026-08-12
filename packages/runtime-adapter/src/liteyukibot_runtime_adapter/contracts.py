"""Public contracts implemented by separately published Python adapter packages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from liteyukibot.events import ActionEnvelope, EventEnvelope
from liteyukibot.runtime.protocol import JsonValue

EventEmitter = Callable[[EventEnvelope], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AdapterContext:
    """Immutable identity and opaque configuration for one adapter instance."""

    runtime_id: str
    instance_id: str
    kind: str
    bot_id: str
    config: Mapping[str, JsonValue]


class AdapterConnection(Protocol):
    """One live platform connection; SDK objects never leave this process."""

    async def start(self, emit: EventEmitter) -> None:
        """Connect and return only after the adapter can accept Actions."""

    async def execute(self, action: ActionEnvelope) -> JsonValue:
        """Execute one Action already routed to this connection's bot ID."""

    async def close(self) -> None:
        """Release platform connections and background tasks."""


AdapterFactory = Callable[[AdapterContext], Awaitable[AdapterConnection]]


@dataclass(frozen=True, slots=True)
class AdapterPlugin:
    """One installable platform or protocol adapter discovered by entry point."""

    kind: str
    create: AdapterFactory

    def __post_init__(self) -> None:
        if not self.kind or self.kind != self.kind.strip():
            raise ValueError("adapter kind must be a non-empty trimmed string")
        if not callable(self.create):
            raise TypeError("adapter factory must be callable")


__all__ = ["AdapterConnection", "AdapterContext", "AdapterFactory", "AdapterPlugin", "EventEmitter"]
