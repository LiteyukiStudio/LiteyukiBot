from __future__ import annotations

from collections.abc import Mapping

import pytest
from liteyukibot_agent.broker import ToolBroker

from liteyukibot.agents import AgentTool, AgentToolResult
from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope


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
