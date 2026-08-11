"""Kernel-owned contracts for separately distributed agent harness packages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .events import EventEnvelope, JsonValue
from .services import ServiceKey

AGENT_TOOL_BROKER_SERVICE = ServiceKey("liteyukibot.agent_tool_broker", 1)


@dataclass(frozen=True, slots=True)
class AgentToolResult:
    """The broker result returned through the capability-gated runtime channel."""

    ok: bool
    data: JsonValue = None
    error: str | None = None


AgentToolHandler = Callable[[EventEnvelope, Mapping[str, JsonValue]], Awaitable[AgentToolResult]]


@dataclass(frozen=True, slots=True)
class AgentTool:
    """An executable common tool published by a package entry point."""

    id: str
    module_id: str
    title: str
    description: str
    input_schema: Mapping[str, object]
    handler: AgentToolHandler
    required_capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for field, value in (("id", self.id), ("module_id", self.module_id)):
            if not value or value != value.strip():
                raise ValueError(f"agent tool {field} must be a non-empty trimmed string")
        if not self.title.strip() or not self.description.strip():
            raise ValueError("agent tool title and description must be non-empty")
        if self.input_schema.get("type") != "object":
            raise ValueError("agent tool input schema must describe a JSON object")


@runtime_checkable
class AgentToolBroker(Protocol):
    """Resolve and execute a common tool for one kernel-delivered event."""

    async def execute(
        self,
        event: EventEnvelope,
        tool_id: str,
        arguments: Mapping[str, JsonValue],
    ) -> AgentToolResult: ...


@runtime_checkable
class AgentToolCatalog(Protocol):
    """Expose JSON-safe tool metadata without leaking executable handlers."""

    def catalog(self) -> Mapping[str, object]: ...


__all__ = [
    "AGENT_TOOL_BROKER_SERVICE",
    "AgentTool",
    "AgentToolBroker",
    "AgentToolCatalog",
    "AgentToolHandler",
    "AgentToolResult",
]
