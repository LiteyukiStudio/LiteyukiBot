from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from liteyukibot_agent.engine import AgentEngine, ModelReply, ToolCall
from liteyukibot_agent.host import NativeAgentHost, _environment_secret
from liteyukibot_agent.store import ConversationStore

from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope, Message, Segment
from liteyukibot.runtime.protocol import (
    ActionResponse,
    AgentToolResponse,
    EventAccepted,
    EventCompleted,
    EventMessage,
)


class FakeClient:
    def __init__(self) -> None:
        self.sent: list[object] = []
        self.actions: list[dict[str, object]] = []
        self.tool_calls: list[tuple[str, str, Mapping[str, object]]] = []

    async def send(self, message: object) -> None:
        self.sent.append(message)

    async def execute_action(
        self,
        _correlation_id: str,
        payload: dict[str, object],
        *,
        delivery_correlation_id: str | None = None,
    ) -> ActionResponse:
        assert delivery_correlation_id == "delivery-1"
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
        return AgentToolResponse(correlation_id="tool", ok=True, data={"result": "ok"})


class FakeEngine(AgentEngine):
    def __init__(self, replies: Sequence[ModelReply]) -> None:
        self._replies = iter(replies)
        self.calls: list[Sequence[Mapping[str, object]]] = []

    async def complete(self, messages: Sequence[Mapping[str, object]]) -> ModelReply:
        self.calls.append(messages)
        return next(self._replies)


class FailingEngine(AgentEngine):
    async def complete(self, _messages: Sequence[Mapping[str, object]]) -> ModelReply:
        raise RuntimeError("model unavailable")


def _event() -> EventEnvelope:
    return EventEnvelope(
        id="event-1",
        runtime_id="nonebot",
        adapter="onebot",
        bot_id="bot-1",
        type="message",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=ActorRef(id="user-1"),
        message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
    )


@pytest.mark.asyncio
async def test_native_agent_returns_ordered_chunks_to_source_runtime(tmp_path: Path) -> None:
    client = FakeClient()
    host = NativeAgentHost(
        client,  # type: ignore[arg-type]
        FakeEngine((ModelReply(text="abcdef"),)),
        ConversationStore(tmp_path / "history.sqlite3"),
        history_limit=10,
        message_chunk_size=3,
        max_concurrent_events=1,
    )
    event = _event()

    await host._accept_event(EventMessage(correlation_id="delivery-1", payload=event.model_dump(mode="json")))
    await asyncio.gather(*host._tasks)
    await host.close()

    assert client.sent == [
        EventAccepted(correlation_id="delivery-1", status="accepted"),
        EventCompleted(correlation_id="delivery-1", status="completed"),
    ]
    assert [
        action["action"]["message"]["segments"][0]["data"]["text"]  # type: ignore[index]
        for action in client.actions
    ] == ["abc", "def"]
    assert all(action["runtime_id"] == "nonebot" for action in client.actions)


@pytest.mark.asyncio
async def test_native_agent_binds_tool_calls_to_the_delivered_event(tmp_path: Path) -> None:
    client = FakeClient()
    engine = FakeEngine(
        (
            ModelReply(tool_calls=(ToolCall("call-1", "docs.search", {"query": "liteyuki"}),)),
            ModelReply(text="found it"),
        )
    )
    host = NativeAgentHost(
        client,  # type: ignore[arg-type]
        engine,
        ConversationStore(tmp_path / "history.sqlite3"),
        history_limit=10,
        message_chunk_size=100,
        max_concurrent_events=1,
    )
    event = _event()

    await host._accept_event(EventMessage(correlation_id="delivery-1", payload=event.model_dump(mode="json")))
    await asyncio.gather(*host._tasks)
    await host.close()

    assert client.tool_calls == [("delivery-1", "docs.search", {"query": "liteyuki"})]
    assert len(engine.calls) == 2


@pytest.mark.asyncio
async def test_native_agent_reports_terminal_failure_without_leaking_the_task(tmp_path: Path) -> None:
    client = FakeClient()
    host = NativeAgentHost(
        client,  # type: ignore[arg-type]
        FailingEngine(),
        ConversationStore(tmp_path / "history.sqlite3"),
        history_limit=10,
        message_chunk_size=100,
        max_concurrent_events=1,
    )

    await host._accept_event(EventMessage(correlation_id="delivery-1", payload=_event().model_dump(mode="json")))
    tasks = tuple(host._tasks)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    await host.close()

    assert len(results) == 1
    assert isinstance(results[0], RuntimeError)
    assert host._tasks == set()
    assert client.sent == [
        EventAccepted(correlation_id="delivery-1", status="accepted"),
        EventCompleted(
            correlation_id="delivery-1",
            status="failed",
            detail="RuntimeError: model unavailable",
        ),
    ]


def test_conversation_history_is_partitioned_by_runtime_bot_and_conversation(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "history.sqlite3")
    try:
        store.append("onebot", "bot-1", "group:one", "user", "first")
        store.append("onebot", "bot-2", "group:one", "user", "other-bot")

        assert store.messages("onebot", "bot-1", "group:one", limit=10) == [
            {"role": "user", "content": "first"}
        ]
    finally:
        store.close()


def test_native_agent_reads_api_key_only_from_its_configured_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_TEST_KEY", "secret")

    assert _environment_secret({"api_key_env": "AGENT_TEST_KEY"}, "api_key_env", "OPENAI_API_KEY") == "secret"
    with pytest.raises(ValueError, match="not set"):
        _environment_secret({}, "api_key_env", "MISSING_AGENT_TEST_KEY")
