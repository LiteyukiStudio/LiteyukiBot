"""Verify the native agent wheel without workspace sources."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import liteyukibot_agent
from liteyukibot_agent.broker import ToolBroker
from liteyukibot_agent.engine import AgentEngine, ModelReply, ToolCall
from liteyukibot_agent.host import NativeAgentHost
from liteyukibot_agent.store import ConversationStore

import liteyukibot
from liteyukibot.agents import AgentTool, AgentToolResult
from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope, Message, Segment
from liteyukibot.runtime import RuntimeCatalog
from liteyukibot.runtime.protocol import (
    ActionResponse,
    AgentToolResponse,
    EventAccepted,
    EventCompleted,
    EventMessage,
    json_mapping,
)

SOURCE_ROOT = Path(__file__).resolve().parents[1]


class _Permissions:
    def __init__(self, allowed: set[str]) -> None:
        self._allowed = allowed

    def allows(self, _event: EventEnvelope, capability: str) -> bool:
        return capability in self._allowed


class _Client:
    def __init__(self) -> None:
        self.sent: list[object] = []
        self.actions: list[Mapping[str, object]] = []
        self.tool_calls: list[tuple[str, str, Mapping[str, object]]] = []

    async def send(self, message: object) -> None:
        self.sent.append(message)

    async def execute_action(
        self,
        _correlation_id: str,
        payload: Mapping[str, object],
        *,
        delivery_correlation_id: str | None = None,
    ) -> ActionResponse:
        if delivery_correlation_id != "delivery-1":
            raise RuntimeError("agent action was not bound to its source delivery")
        self.actions.append(payload)
        return ActionResponse(correlation_id="action", ok=True)

    async def execute_agent_tool(
        self,
        _correlation_id: str,
        delivery_correlation_id: str,
        tool_id: str,
        arguments: Mapping[str, object],
    ) -> AgentToolResponse:
        self.tool_calls.append((delivery_correlation_id, tool_id, arguments))
        return AgentToolResponse(correlation_id="tool", ok=True, data={"result": "found"})


class _Engine(AgentEngine):
    def __init__(self) -> None:
        self.calls = 0
        self.tools: list[Sequence[Mapping[str, object]]] = []

    async def complete(
        self,
        _messages: Sequence[Mapping[str, object]],
        *,
        tools: Sequence[Mapping[str, object]] = (),
    ) -> ModelReply:
        self.tools.append(tools)
        self.calls += 1
        if self.calls == 1:
            return ModelReply(tool_calls=(ToolCall("call-1", "docs.search", {"query": "liteyuki"}),))
        return ModelReply(text="found it")


def _event() -> EventEnvelope:
    return EventEnvelope(
        id="event-1",
        runtime_id="nonebot",
        adapter="onebot.v11",
        bot_id="bot-1",
        type="message",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=ActorRef(id="user-1"),
        message=Message(segments=(Segment(type="text", data={"text": "search docs"}),)),
    )


async def _verify_agent_contract() -> None:
    calls: list[Mapping[str, object]] = []

    async def search(event: EventEnvelope, arguments: Mapping[str, object]) -> AgentToolResult:
        if event.id != "event-1" or arguments != {"query": "liteyuki"}:
            raise RuntimeError("agent tool handler received an unexpected source event")
        calls.append(arguments)
        return AgentToolResult(ok=True, data={"result": "found"})

    tool = AgentTool(
        id="docs.search",
        module_id="docs",
        title="Search docs",
        description="Search installed documentation.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=search,
        required_capabilities=frozenset({"docs.search"}),
    )
    event = _event()
    denied = ToolBroker({tool.id: tool}, _Permissions(set()))
    if denied.catalog_for(event)["tools"] != []:
        raise RuntimeError("permissioned agent tool leaked into a denied event catalog")
    if (await denied.execute(event, tool.id, {"query": "liteyuki"})).error != "agent tool permission is denied":
        raise RuntimeError("permissioned agent tool execution was not denied")

    broker = ToolBroker({tool.id: tool}, _Permissions({"docs.search"}))
    catalog = broker.catalog_for(event)
    result = await broker.execute(event, tool.id, {"query": "liteyuki"})
    if result != AgentToolResult(ok=True, data={"result": "found"}) or calls != [{"query": "liteyuki"}]:
        raise RuntimeError("authorized agent tool did not execute through the broker")

    client = _Client()
    engine = _Engine()
    with tempfile.TemporaryDirectory() as directory:
        host = NativeAgentHost(
            client,  # type: ignore[arg-type]
            engine,
            ConversationStore(Path(directory) / "history.sqlite3"),
            history_limit=10,
            message_chunk_size=100,
            max_concurrent_events=1,
        )
        await host._accept_event(
            EventMessage(
                correlation_id="delivery-1",
                payload=event.model_dump(mode="json"),
                agent_tool_catalog=json_mapping(catalog),
            )
        )
        await asyncio.gather(*host._tasks)
        await host.close()

    expected_schema = {
        "type": "function",
        "function": {
            "name": "docs.search",
            "description": "Search installed documentation.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
    }
    if engine.tools != [(expected_schema,), (expected_schema,)]:
        raise RuntimeError("agent harness did not pass the event-specific catalog to every model turn")
    if client.tool_calls != [("delivery-1", "docs.search", {"query": "liteyuki"})]:
        raise RuntimeError("agent tool request was not bound to its source delivery")
    if client.sent != [
        EventAccepted(correlation_id="delivery-1", status="accepted"),
        EventCompleted(correlation_id="delivery-1", status="completed"),
    ]:
        raise RuntimeError("agent event did not reach the expected terminal protocol state")
    if len(client.actions) != 1 or client.actions[0].get("runtime_id") != "nonebot":
        raise RuntimeError("agent reply was not routed through the source runtime")


def verify(expected_version: str | None = None) -> None:
    imported = (Path(liteyukibot.__file__).resolve(), Path(liteyukibot_agent.__file__).resolve())
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")
    plugin = RuntimeCatalog().discover().get("agent")
    if plugin is None or plugin.agent_harness != "native":
        raise RuntimeError("native agent runtime entry point was not discovered")
    observed = {
        name: importlib.metadata.version(name)
        for name in ("liteyukibot-v7", "liteyukibot-v7-agent", "liteyukibot-v7-agent-resolver")
    }
    if expected_version is not None and observed["liteyukibot-v7-agent"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-agent {expected_version}; observed {observed}")
    asyncio.run(_verify_agent_contract())
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(arguments.expected_version)
