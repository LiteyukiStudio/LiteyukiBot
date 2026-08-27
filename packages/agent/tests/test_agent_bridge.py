from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from liteyukibot_agent.catalog import AgentCatalog
from liteyukibot_agent.engine import AgentEngine, ModelReply, ToolCall
from liteyukibot_agent.host import AGENT_HISTORY_CLEAR, AGENT_PROMPT_SELECT, AgentBridgeHost
from liteyukibot_agent.store import ConversationStore
from liteyukibot_agent_resolver import AgentToolDescriptor
from liteyukibot_broker import (
    ActionResult,
    AuthorizationContextWire,
    BridgeControlInvoke,
    BridgeControlResult,
    BrokerBridgeRunner,
    BrokerDelivery,
    BrokerEvent,
    EventMessage,
    ToolResult,
)

from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope, Message, Segment


class FakeEngine(AgentEngine):
    def __init__(self, replies: Sequence[ModelReply]) -> None:
        self._replies = iter(replies)
        self.tools: list[Sequence[Mapping[str, object]]] = []
        self.messages: list[Sequence[Mapping[str, object]]] = []

    async def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        tools: Sequence[Mapping[str, object]] = (),
    ) -> ModelReply:
        self.messages.append(messages)
        self.tools.append(tools)
        return next(self._replies)


class FakePermissions:
    def allows(self, _context: object, _capability: str) -> bool:
        return True


class FakeRunner:
    def __init__(self) -> None:
        self.actions: list[Mapping[str, object]] = []
        self.tools: list[tuple[str, Mapping[str, object]]] = []
        self.control_result: BridgeControlResult | None = None
        self.tool_result: ToolResult | None = None

    async def request_action(self, **kwargs: Any) -> ActionResult:
        self.actions.append(cast(Mapping[str, object], kwargs["payload"]))
        return ActionResult(action_id="action-1", success=True, payload={"message_id": "sent-1"})

    async def request_tool(self, **kwargs: Any) -> ToolResult:
        self.tools.append((str(kwargs["tool_id"]), cast(Mapping[str, object], kwargs["arguments"])))
        return self.tool_result or ToolResult(invocation_id="invocation-1", success=True, result={"answer": "ok"})

    async def request_control(self, **_kwargs: Any) -> BridgeControlResult:
        return self.control_result or BridgeControlResult(
            invocation_id="control-1", success=False, error_code="CONTROL_NO_OWNER"
        )


def _event() -> EventEnvelope:
    return EventEnvelope(
        id="source-event-1",
        runtime_id="nonebot",
        adapter="onebot.v11",
        bot_id="bot-1",
        type="message",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=ActorRef(id="user-1"),
        message=Message(segments=(Segment(type="text", data={"text": "find it"}),)),
        reply_token="reply-1",
    )


def _delivery(event: EventEnvelope) -> BrokerDelivery:
    broker_event = BrokerEvent(
        kernel_event_id="kernel-event-1",
        source_bridge_id="nonebot",
        source_event_id=event.id,
        topic="message.created",
        ordering_key=event.conversation.ordering_key,
        payload=event.model_dump(mode="json"),
    )
    return BrokerDelivery(
        cast(BrokerBridgeRunner, FakeRunner()),
        EventMessage(delivery_id="delivery-1", lease_id="lease-1", lease_ttl_ms=10_000, event=broker_event),
    )


def _tool() -> AgentToolDescriptor:
    return AgentToolDescriptor(
        id="docs.search",
        module_id="docs",
        title="Search docs",
        description="Search installed docs.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
    )


@pytest.mark.asyncio
async def test_agent_bridge_emits_one_final_message_and_routes_tool_through_delivery(tmp_path: Path) -> None:
    runner = FakeRunner()
    event = _event()
    delivery = _delivery(event)
    delivery = BrokerDelivery(cast(BrokerBridgeRunner, runner), delivery.message)
    store = ConversationStore(tmp_path / "history.sqlite3")
    host = AgentBridgeHost(
        cast(BrokerBridgeRunner, runner),
        FakeEngine(
            (
                ModelReply(tool_calls=(ToolCall("call-1", "docs.search", {"query": "liteyuki"}),)),
                ModelReply(text="found it"),
            )
        ),
        store,
        AgentCatalog((_tool(),)),
        FakePermissions(),
        max_concurrent_events=1,
        history_limit=10,
        model_timeout_seconds=1,
        event_timeout_seconds=2,
        max_tool_rounds=2,
    )
    try:
        await host.handle_delivery(delivery)
        assert runner.tools == [("docs.search", {"query": "liteyuki"})]
        assert len(runner.actions) == 1
        assert runner.actions[0]["reply_token"] == "reply-1"
        history = store.messages("nonebot", "bot-1", "group:group-1", limit=10)
        assert [item["role"] for item in history] == ["user", "tool", "assistant"]
        assert "query" not in str(history[1])
    finally:
        store.close()


@pytest.mark.asyncio
async def test_agent_history_control_checks_context_and_clears_one_conversation(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "history.sqlite3")
    store.append("nonebot", "bot-1", "group:group-1", "user", "hello", retain=10)
    host = AgentBridgeHost(
        cast(BrokerBridgeRunner, FakeRunner()),
        FakeEngine((ModelReply(text="unused"),)),
        store,
        AgentCatalog(),
        FakePermissions(),
        max_concurrent_events=1,
        history_limit=10,
        model_timeout_seconds=1,
        event_timeout_seconds=2,
        max_tool_rounds=1,
    )
    request = BridgeControlInvoke(
        delivery_id="delivery-1",
        lease_id="lease-1",
        correlation_id="clear-1",
        command=AGENT_HISTORY_CLEAR,
        authorization=AuthorizationContextWire(
            event_id="kernel-event-1",
            runtime_id="nonebot",
            bot_id="bot-1",
            actor_id="user-1",
        ),
        payload={
            "runtime_id": "nonebot",
            "bot_id": "bot-1",
            "conversation_id": "group:group-1",
        },
    )
    try:
        invalid = request.model_copy(
            update={
                "payload": {
                    "runtime_id": "other-runtime",
                    "bot_id": "bot-1",
                    "conversation_id": "group:group-1",
                }
            }
        )
        invalid_result = await host.clear_history(invalid)
        assert invalid_result.success is False
        assert invalid_result.error_code == "CONTROL_INVALID_PAYLOAD"
        result = await host.clear_history(request)
        assert result.success is True
        assert result.result == {"cleared": 1}
        assert store.messages("nonebot", "bot-1", "group:group-1", limit=10) == []
    finally:
        store.close()


@pytest.mark.asyncio
async def test_agent_bridge_adds_rag_context_and_optional_citations(tmp_path: Path) -> None:
    from liteyukibot_agent.rag import RagIndex, RagSettings

    class FakeEmbeddings:
        async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
            return tuple((1.0, 0.0) if "facts" in text.casefold() else (0.0, 1.0) for text in texts)

    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "facts.txt").write_text("facts from local docs", encoding="utf-8")
    settings = RagSettings.from_options(
        {
            "rag_paths": [str(documents)],
            "rag_index_path": str(tmp_path / "rag.sqlite3"),
            "rag_embedding_api_key": "test-key",
            "rag_citations": True,
        },
        default_directory=tmp_path,
    )
    assert settings is not None
    rag = RagIndex(settings, FakeEmbeddings())
    await rag.sync()
    runner = FakeRunner()
    engine = FakeEngine((ModelReply(text="answer"),))
    store = ConversationStore(tmp_path / "history.sqlite3")
    host = AgentBridgeHost(
        cast(BrokerBridgeRunner, runner),
        engine,
        store,
        AgentCatalog(),
        FakePermissions(),
        max_concurrent_events=1,
        history_limit=10,
        model_timeout_seconds=1,
        event_timeout_seconds=2,
        max_tool_rounds=1,
        rag=rag,
    )
    event = _event().model_copy(update={"message": Message(segments=(Segment(type="text", data={"text": "facts"}),))})
    delivery = BrokerDelivery(cast(BrokerBridgeRunner, runner), _delivery(event).message)
    try:
        await host.handle_delivery(delivery)
        assert engine.messages[0][0] == {
            "role": "system",
            "content": "Relevant local documents:\n[root-0/facts.txt#0] facts from local docs",
        }
        payload = cast(Mapping[str, Any], runner.actions[0])
        message = cast(Mapping[str, Any], payload["message"])
        segments = cast(Sequence[Mapping[str, Any]], message["segments"])
        data = cast(Mapping[str, Any], segments[0]["data"])
        assert data["text"] == "answer\n\nSources: root-0/facts.txt#0"
    finally:
        rag.close()
        store.close()


@pytest.mark.asyncio
async def test_agent_bridge_activates_kernel_functions_and_applies_selected_prompt(tmp_path: Path) -> None:
    runner = FakeRunner()
    runner.control_result = BridgeControlResult(
        invocation_id="catalog-1",
        success=True,
        result=cast(Any, {
            "tools": [
                {
                    "id": "example.lyf.say",
                    "module_id": "example",
                    "title": "say",
                    "description": "Say a greeting.",
                    "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}},
                    "required_capabilities": [],
                }
            ],
            "prompts": [
                {
                    "id": "friendly",
                    "name": "Friendly",
                    "description": "Friendly voice.",
                    "prompt": "Answer in a friendly voice.",
                    "examples": [],
                }
            ],
        }),
    )
    runner.tool_result = ToolResult(invocation_id="invocation-1", success=True, result={"preset_id": "friendly"})
    engine = FakeEngine(
        (
            ModelReply(tool_calls=(ToolCall("call-1", "example.lyf.say", {"name": "world"}),)),
            ModelReply(text="hello"),
        )
    )
    store = ConversationStore(tmp_path / "history.sqlite3")
    host = AgentBridgeHost(
        cast(BrokerBridgeRunner, runner),
        engine,
        store,
        AgentCatalog(),
        FakePermissions(),
        max_concurrent_events=1,
        history_limit=10,
        model_timeout_seconds=1,
        event_timeout_seconds=2,
        max_tool_rounds=2,
    )
    event = _event()
    delivery = BrokerDelivery(cast(BrokerBridgeRunner, runner), _delivery(event).message)
    try:
        await host.handle_delivery(delivery)
        assert runner.tools == [("example.lyf.say", {"name": "world"})]
        assert any(
            item.get("role") == "system" and item.get("content") == "Answer in a friendly voice."
            for item in engine.messages[1]
        )
    finally:
        store.close()


@pytest.mark.asyncio
async def test_agent_prompt_control_accepts_only_active_verified_preset(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "history.sqlite3")
    host = AgentBridgeHost(
        cast(BrokerBridgeRunner, FakeRunner()),
        FakeEngine((ModelReply(text="unused"),)),
        store,
        AgentCatalog(),
        FakePermissions(),
        max_concurrent_events=1,
        history_limit=10,
        model_timeout_seconds=1,
        event_timeout_seconds=2,
        max_tool_rounds=1,
    )
    host._active_prompt_catalogs["kernel-event-1"] = {"friendly": {"prompt": "safe", "examples": ()}}
    request = BridgeControlInvoke(
        delivery_id="delivery-1",
        lease_id="lease-1",
        correlation_id="prompt-1",
        command=AGENT_PROMPT_SELECT,
        authorization=AuthorizationContextWire(
            event_id="kernel-event-1",
            runtime_id="nonebot",
            bot_id="bot-1",
            actor_id="user-1",
        ),
        payload={"preset_id": "friendly"},
    )
    try:
        result = await host.select_prompt(request)
        assert result.success is True
        assert result.result == {"preset_id": "friendly"}
        invalid = await host.select_prompt(request.model_copy(update={"payload": {"preset_id": "unknown"}}))
        assert invalid.success is False
        assert invalid.error_code == "CONTROL_NOT_FOUND"
    finally:
        store.close()
