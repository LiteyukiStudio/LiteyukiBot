from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from liteyukibot_agent import runtime_plugin
from liteyukibot_agent.engine import AgentEngine, ModelReply, ToolCall
from liteyukibot_agent.host import NativeAgentHost, _environment_secret
from liteyukibot_agent.store import ConversationStore

from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope, Message, Segment
from liteyukibot.runtime import ActionSinkResult, AgentToolSinkResult, RuntimeSpec
from liteyukibot.runtime.protocol import (
    ActionResponse,
    AgentToolResponse,
    ControlRequest,
    ControlResponse,
    EventAccepted,
    EventCompleted,
    EventMessage,
    JsonValue,
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
        self.tools: list[Sequence[Mapping[str, object]]] = []

    async def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        tools: Sequence[Mapping[str, object]] = (),
    ) -> ModelReply:
        self.calls.append(messages)
        self.tools.append(tools)
        return next(self._replies)


class FailingEngine(AgentEngine):
    async def complete(
        self,
        _messages: Sequence[Mapping[str, object]],
        *,
        tools: Sequence[Mapping[str, object]] = (),
    ) -> ModelReply:
        raise RuntimeError("model unavailable")


class BlockingEngine(AgentEngine):
    async def complete(
        self,
        _messages: Sequence[Mapping[str, object]],
        *,
        tools: Sequence[Mapping[str, object]] = (),
    ) -> ModelReply:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


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


async def _read_http_request(reader: asyncio.StreamReader) -> tuple[str, dict[str, object]]:
    header = await reader.readuntil(b"\r\n\r\n")
    lines = header.decode("ascii").split("\r\n")
    content_length = next(
        int(line.split(":", 1)[1].strip())
        for line in lines
        if line.lower().startswith("content-length:")
    )
    return lines[0], json.loads((await reader.readexactly(content_length)).decode("utf-8"))


async def _write_completion(
    writer: asyncio.StreamWriter,
    message: dict[str, object],
) -> None:
    payload = json.dumps({"choices": [{"message": message}]}).encode("utf-8")
    writer.write(
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        + f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode("ascii")
        + payload
    )
    await writer.drain()
    writer.close()
    await writer.wait_closed()


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

    await host._accept_event(
        EventMessage(
            correlation_id="delivery-1",
            payload=event.model_dump(mode="json"),
            agent_tool_catalog={
                "tools": [
                    {
                        "id": "docs.search",
                        "description": "Search docs.",
                        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                    }
                ]
            },
        )
    )
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

    await host._accept_event(
        EventMessage(
            correlation_id="delivery-1",
            payload=event.model_dump(mode="json"),
            agent_tool_catalog={
                "tools": [
                    {
                        "id": "docs.search",
                        "description": "Search docs.",
                        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                    }
                ]
            },
        )
    )
    await asyncio.gather(*host._tasks)
    await host.close()

    assert client.tool_calls == [("delivery-1", "docs.search", {"query": "liteyuki"})]
    assert len(engine.calls) == 2
    assert engine.tools == [
        (
            {
                "type": "function",
                "function": {
                    "name": "docs.search",
                    "description": "Search docs.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            },
        ),
        (
            {
                "type": "function",
                "function": {
                    "name": "docs.search",
                    "description": "Search docs.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            },
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.skip(
    reason="native agent child-supervisor integration is not selected by config v5; broker-peer coverage follows B5-5"
)
async def test_native_agent_child_round_trips_mock_provider_tool_and_source_action(tmp_path: Path) -> None:
    requests: list[dict[str, object]] = []
    responses: Sequence[dict[str, object]] = (
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "docs.search",
                        "arguments": '{"query":"liteyuki","limit":true}',
                    },
                }
            ],
        },
        {"role": "assistant", "content": "found it", "tool_calls": []},
    )
    response_iterator = iter(responses)

    async def provider(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_line, request = await _read_http_request(reader)
        assert request_line == "POST /v1/chat/completions HTTP/1.1"
        requests.append(request)
        await _write_completion(writer, next(response_iterator))

    server = await asyncio.start_server(provider, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    observed_tools: list[tuple[str, str, str, Mapping[str, JsonValue]]] = []
    observed_actions: list[Mapping[str, JsonValue]] = []

    async def tool_sink(
        runtime_id: str,
        delivery_id: str,
        payload: dict[str, JsonValue],
        tool_id: str,
        arguments: dict[str, JsonValue],
    ) -> AgentToolSinkResult:
        observed_tools.append((runtime_id, delivery_id, str(payload["id"]), arguments))
        assert tool_id == "docs.search"
        return AgentToolSinkResult(ok=True, data={"result": "found"})

    async def action_sink(_runtime_id: str, payload: dict[str, JsonValue]) -> ActionSinkResult:
        observed_actions.append(payload)
        return ActionSinkResult(ok=True)

    spec = RuntimeSpec(
        id="agent",
        kind="agent",
        command=(sys.executable, "-m", "liteyukibot_agent"),
        env={
            "LITEYUKI_AGENT_API_KEY": "test-key",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
            "NO_PROXY": "*",
            "http_proxy": "",
            "https_proxy": "",
            "all_proxy": "",
            "no_proxy": "*",
        },
        options={
            "model": "mock-model",
            "base_url": f"http://127.0.0.1:{port}/v1",
            "history_limit": 10,
            "message_chunk_size": 100,
            "max_concurrent_events": 1,
            "model_timeout_seconds": 10,
            "event_timeout_seconds": 15,
        },
        heartbeat_interval=0.05,
        stale_after=1,
        ready_timeout=5,
        shutdown_timeout=2,
        agent_harness="native",
    )
    from liteyukibot.testing import RuntimeTestHarness

    harness = RuntimeTestHarness(
        spec,
        action_sink=action_sink,
        agent_tool_sink=tool_sink,
    )
    try:
        async with harness:
            accepted = await harness.dispatch_event(
                _event().model_dump(mode="json"),
                correlation_id="delivery-1",
                agent_tool_catalog={
                    "tools": [
                        {
                            "id": "docs.search",
                            "description": "Search docs.",
                            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                        }
                    ]
                },
            )
            assert accepted == EventAccepted(correlation_id="delivery-1", status="accepted")
            completed = await harness.wait_for_delivery_completion("delivery-1", timeout_seconds=12)
            assert completed == EventCompleted(correlation_id="delivery-1", status="completed")
    finally:
        server.close()
        await server.wait_closed()

    assert observed_tools == [("agent", "delivery-1", "event-1", {"query": "liteyuki", "limit": True})]
    assert observed_actions[0]["runtime_id"] == "nonebot"
    assert len(requests) == 2
    assert requests[0]["model"] == "mock-model"
    assert requests[0]["tools"] != []
    second_messages = requests[1]["messages"]
    assert isinstance(second_messages, list)
    assistant_message = second_messages[-2]
    assert isinstance(assistant_message, dict)
    tool_calls = assistant_message["tool_calls"]
    assert isinstance(tool_calls, list) and len(tool_calls) == 1
    tool_call = tool_calls[0]
    assert isinstance(tool_call, dict)
    function = tool_call["function"]
    assert isinstance(function, dict)
    arguments = function["arguments"]
    assert arguments == '{"query":"liteyuki","limit":true}'
    assert json.loads(arguments) == {"query": "liteyuki", "limit": True}


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


@pytest.mark.asyncio
async def test_native_agent_bounds_a_stalled_model_request_and_releases_capacity(tmp_path: Path) -> None:
    client = FakeClient()
    host = NativeAgentHost(
        client,  # type: ignore[arg-type]
        BlockingEngine(),
        ConversationStore(tmp_path / "history.sqlite3"),
        history_limit=10,
        message_chunk_size=100,
        max_concurrent_events=1,
        model_timeout_seconds=0.01,
        event_timeout_seconds=1,
    )

    await host._accept_event(EventMessage(correlation_id="delivery-1", payload=_event().model_dump(mode="json")))
    results = await asyncio.gather(*tuple(host._tasks), return_exceptions=True)
    await host.close()

    assert len(results) == 1
    assert isinstance(results[0], RuntimeError)
    assert str(results[0]) == "agent model request timed out"
    assert host._tasks == set()
    assert client.sent == [
        EventAccepted(correlation_id="delivery-1", status="accepted"),
        EventCompleted(
            correlation_id="delivery-1",
            status="failed",
            detail="RuntimeError: agent model request timed out",
        ),
    ]


@pytest.mark.asyncio
async def test_native_agent_bounds_the_entire_event_lifecycle(tmp_path: Path) -> None:
    client = FakeClient()
    host = NativeAgentHost(
        client,  # type: ignore[arg-type]
        BlockingEngine(),
        ConversationStore(tmp_path / "history.sqlite3"),
        history_limit=10,
        message_chunk_size=100,
        max_concurrent_events=1,
        model_timeout_seconds=1,
        event_timeout_seconds=0.01,
    )

    await host._accept_event(EventMessage(correlation_id="delivery-1", payload=_event().model_dump(mode="json")))
    results = await asyncio.gather(*tuple(host._tasks), return_exceptions=True)
    await host.close()

    assert len(results) == 1
    assert isinstance(results[0], TimeoutError)
    assert host._tasks == set()
    assert client.sent == [
        EventAccepted(correlation_id="delivery-1", status="accepted"),
        EventCompleted(correlation_id="delivery-1", status="failed", detail="agent event timed out"),
    ]


@pytest.mark.asyncio
async def test_native_agent_uses_the_configured_tool_round_limit(tmp_path: Path) -> None:
    client = FakeClient()
    host = NativeAgentHost(
        client,  # type: ignore[arg-type]
        FakeEngine(
            (
                ModelReply(tool_calls=(ToolCall("call-1", "docs.search", {}),)),
                ModelReply(tool_calls=(ToolCall("call-2", "docs.search", {}),)),
            )
        ),
        ConversationStore(tmp_path / "history.sqlite3"),
        history_limit=10,
        message_chunk_size=100,
        max_concurrent_events=1,
        max_tool_rounds=1,
    )

    await host._accept_event(EventMessage(correlation_id="delivery-1", payload=_event().model_dump(mode="json")))
    results = await asyncio.gather(*tuple(host._tasks), return_exceptions=True)
    await host.close()

    assert len(results) == 1
    assert isinstance(results[0], RuntimeError)
    assert str(results[0]) == "agent exceeded maximum tool-call rounds"
    assert client.tool_calls == [("delivery-1", "docs.search", {})]


def test_conversation_history_is_partitioned_by_runtime_bot_and_conversation(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "history.sqlite3")
    try:
        store.append("onebot", "bot-1", "group:one", "user", "first", retain=10)
        store.append("onebot", "bot-2", "group:one", "user", "other-bot", retain=10)

        assert store.messages("onebot", "bot-1", "group:one", limit=10) == [
            {"role": "user", "content": "first"}
        ]
    finally:
        store.close()


def test_conversation_history_is_bounded_and_can_clear_one_source_conversation(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "history.sqlite3")
    try:
        for value in ("first", "second", "third"):
            store.append("onebot", "bot-1", "group:one", "user", value, retain=2)
        store.append("onebot", "bot-1", "group:two", "user", "unrelated", retain=2)

        assert store.messages("onebot", "bot-1", "group:one", limit=10) == [
            {"role": "user", "content": "second"},
            {"role": "user", "content": "third"},
        ]
        assert store.clear("onebot", "bot-1", "group:one") == 2
        assert store.messages("onebot", "bot-1", "group:one", limit=10) == []
        assert store.messages("onebot", "bot-1", "group:two", limit=10) == [
            {"role": "user", "content": "unrelated"}
        ]
        with pytest.raises(ValueError, match="retention"):
            store.append("onebot", "bot-1", "group:one", "user", "invalid", retain=0)
    finally:
        store.close()


def test_native_agent_control_clears_only_the_requested_history(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "history.sqlite3")
    host = NativeAgentHost(
        FakeClient(),  # type: ignore[arg-type]
        FakeEngine(()),
        store,
        history_limit=10,
        message_chunk_size=100,
        max_concurrent_events=1,
    )
    try:
        store.append("onebot", "42", "group:2002", "user", "first", retain=10)
        store.append("onebot", "42", "group:2002", "assistant", "second", retain=10)
        store.append("onebot", "43", "group:2002", "user", "other bot", retain=10)

        response = host._execute_control(
            ControlRequest(
                correlation_id="clear-1",
                command="agent.history.clear",
                payload={"runtime_id": "onebot", "bot_id": "42", "conversation_id": "group:2002"},
            )
        )
        assert response == ControlResponse(correlation_id="clear-1", ok=True, data={"cleared": 2})
        assert store.messages("onebot", "42", "group:2002", limit=10) == []
        assert store.messages("onebot", "43", "group:2002", limit=10) == [
            {"role": "user", "content": "other bot"}
        ]

        invalid = host._execute_control(
            ControlRequest(
                correlation_id="clear-2",
                command="agent.history.clear",
                payload={"runtime_id": "onebot", "bot_id": "42", "conversation_id": ""},
            )
        )
        assert invalid == ControlResponse(
            correlation_id="clear-2", ok=False, error="invalid agent history clear request"
        )
    finally:
        store.close()


def test_native_agent_reads_api_key_only_from_its_configured_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_TEST_KEY", "secret")

    assert _environment_secret({"api_key_env": "AGENT_TEST_KEY"}, "api_key_env", "OPENAI_API_KEY") == "secret"
    with pytest.raises(ValueError, match="not set"):
        _environment_secret({}, "api_key_env", "MISSING_AGENT_TEST_KEY")


def test_native_agent_runtime_metadata_exposes_bounded_options() -> None:
    plugin = runtime_plugin()
    assert plugin.init_spec is not None

    fields = {field.key: field for field in plugin.init_spec.fields}
    assert fields["model_timeout_seconds"].default == 60
    assert fields["event_timeout_seconds"].default == 120
    assert fields["max_tool_rounds"].default == 4
    assert fields["history_limit"].default == 40
    assert fields["max_concurrent_events"].default == 16
