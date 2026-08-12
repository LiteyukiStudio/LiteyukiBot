from __future__ import annotations

from collections.abc import Mapping

import pytest
from liteyukibot_agent.broker import ToolBroker

from liteyukibot.agents import AgentTool, AgentToolResult
from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope


class FakePermissions:
    def __init__(self, allowed: set[str]) -> None:
        self.allowed = allowed

    def allows(self, _event: EventEnvelope, capability: str) -> bool:
        return capability in self.allowed


def _event() -> EventEnvelope:
    return EventEnvelope(
        runtime_id="nonebot",
        adapter="onebot",
        bot_id="bot-1",
        type="message",
        conversation=ConversationRef(id="conversation"),
        actor=ActorRef(id="actor"),
    )


@pytest.mark.asyncio
async def test_broker_rejects_unregistered_and_permissioned_tools_by_default() -> None:
    async def handler(_event: EventEnvelope, _arguments: Mapping[str, object]) -> AgentToolResult:
        return AgentToolResult(ok=True, data={"ok": True})

    tool = AgentTool(
        id="admin.reset",
        module_id="admin",
        title="Reset",
        description="Reset data.",
        input_schema={"type": "object", "properties": {}},
        handler=handler,
        required_capabilities=frozenset({"admin.reset"}),
    )
    broker = ToolBroker({tool.id: tool}, permissions=None)

    assert (await broker.execute(_event(), "missing", {})).error == "agent tool is not registered"
    assert (await broker.execute(_event(), "admin.reset", {})).error == "agent tool permission is denied"


@pytest.mark.asyncio
async def test_broker_catalog_for_exposes_only_tools_authorized_for_the_event() -> None:
    async def handler(_event: EventEnvelope, _arguments: Mapping[str, object]) -> AgentToolResult:
        return AgentToolResult(ok=True)

    public = AgentTool(
        id="docs.search",
        module_id="docs",
        title="Search",
        description="Search docs.",
        input_schema={"type": "object", "properties": {}},
        handler=handler,
    )
    protected = AgentTool(
        id="admin.reset",
        module_id="admin",
        title="Reset",
        description="Reset data.",
        input_schema={"type": "object", "properties": {}},
        handler=handler,
        required_capabilities=frozenset({"admin.reset"}),
    )
    event = _event()
    denied = ToolBroker({public.id: public, protected.id: protected}, FakePermissions(set()))
    allowed = ToolBroker({public.id: public, protected.id: protected}, FakePermissions({"admin.reset"}))

    denied_tools = denied.catalog_for(event)["tools"]
    allowed_tools = allowed.catalog_for(event)["tools"]
    assert isinstance(denied_tools, list)
    assert isinstance(allowed_tools, list)
    assert [item["id"] for item in denied_tools if isinstance(item, Mapping)] == ["docs.search"]
    assert [item["id"] for item in allowed_tools if isinstance(item, Mapping)] == [
        "admin.reset",
        "docs.search",
    ]
    assert (await denied.execute(event, "admin.reset", {})).error == "agent tool permission is denied"
    assert (await allowed.execute(event, "admin.reset", {})).ok is True
