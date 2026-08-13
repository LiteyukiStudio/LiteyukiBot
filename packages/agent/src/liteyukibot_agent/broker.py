"""Kernel-side execution broker for common package-provided agent tools."""

from __future__ import annotations

from collections.abc import Mapping
from importlib import metadata
from typing import Any, Protocol, cast

from liteyukibot.agents import AgentTool, AgentToolResult
from liteyukibot.events import EventEnvelope, JsonValue


class PermissionChecker(Protocol):
    def allows(self, event: EventEnvelope, capability: str) -> bool: ...


class ToolBroker:
    """Fail-closed executable registry loaded from installed tool distributions."""

    ENTRY_POINT_GROUP = "liteyukibot.agent_tools"

    def __init__(self, tools: Mapping[str, AgentTool], permissions: PermissionChecker | None) -> None:
        self._tools = dict(tools)
        self._permissions = permissions

    @classmethod
    def discover(cls, permissions: PermissionChecker | None = None) -> ToolBroker:
        tools: dict[str, AgentTool] = {}
        for entry in metadata.entry_points(group=cls.ENTRY_POINT_GROUP):
            loaded = entry.load()
            if not callable(loaded):
                raise RuntimeError(f"agent tool entry point {entry.name!r} is not callable")
            tool = loaded()
            if not isinstance(tool, AgentTool):
                raise RuntimeError(f"agent tool entry point {entry.name!r} did not return AgentTool")
            if tool.id != entry.name:
                raise RuntimeError(f"agent tool entry point {entry.name!r} returned mismatched id {tool.id!r}")
            if tool.id in tools:
                raise RuntimeError(f"duplicate agent tool id {tool.id!r}")
            tools[tool.id] = tool
        return cls(tools, permissions)

    async def execute(
        self,
        event: EventEnvelope,
        tool_id: str,
        arguments: Mapping[str, JsonValue],
    ) -> AgentToolResult:
        tool = self._tools.get(tool_id)
        if tool is None:
            return AgentToolResult(ok=False, error="agent tool is not registered")
        if not self._allowed(event, tool, audit=True):
            return AgentToolResult(ok=False, error="agent tool permission is denied")
        try:
            result = await tool.handler(event, arguments)
        except Exception:
            return AgentToolResult(ok=False, error="agent tool execution failed")
        if not isinstance(result, AgentToolResult):
            return AgentToolResult(ok=False, error="agent tool returned an invalid result")
        return result

    def catalog(self) -> Mapping[str, object]:
        """Return public schemas only; permissioned tools remain invisible by default."""

        return {
            "tools": [
                {
                    "id": tool.id,
                    "title": tool.title,
                    "description": tool.description,
                    "input_schema": dict(tool.input_schema),
                }
                for tool in sorted(self._tools.values(), key=lambda candidate: candidate.id)
                if not tool.required_capabilities
            ]
        }

    def catalog_for(self, event: EventEnvelope) -> Mapping[str, object]:
        """Return exactly the schemas that this event principal may invoke."""

        return {
            "tools": [
                {
                    "id": tool.id,
                    "title": tool.title,
                    "description": tool.description,
                    "input_schema": dict(tool.input_schema),
                }
                for tool in sorted(self._tools.values(), key=lambda candidate: candidate.id)
                if self._allowed(event, tool)
            ]
        }

    def _allowed(self, event: EventEnvelope, tool: AgentTool, *, audit: bool = False) -> bool:
        if not tool.required_capabilities:
            return True
        if self._permissions is None:
            return False
        for capability in tool.required_capabilities:
            decide = getattr(self._permissions, "decide", None)
            if audit and callable(decide):
                allowed = decide(event, capability, component="agent.tool")
            else:
                allowed = self._permissions.allows(event, capability)
            if not allowed:
                return False
        return True


def permission_checker(service: object | None) -> PermissionChecker | None:
    if service is None:
        return None
    candidate = cast(Any, service)
    if not callable(getattr(candidate, "allows", None)):
        raise RuntimeError("permission service has an invalid implementation")
    return cast(PermissionChecker, candidate)
