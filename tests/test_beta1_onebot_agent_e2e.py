"""Beta1 acceptance path: OneBot HTTP -> Agent child -> tool -> OneBot action."""

from __future__ import annotations

import asyncio
import importlib
import json
import socket
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from liteyukibot_agent.broker import ToolBroker

from liteyukibot.agents import AgentTool, AgentToolResult
from liteyukibot.app import LiteyukiApp
from liteyukibot.config import AgentSettings, AppSettings, CoreSettings, PluginSettings, RuntimeSettings
from liteyukibot.events import EventEnvelope


@dataclass(frozen=True, slots=True)
class HttpRequest:
    path: str
    payload: Mapping[str, Any]


class _HttpStub:
    def __init__(self, responses: Sequence[Mapping[str, object]]) -> None:
        self.requests: asyncio.Queue[HttpRequest] = asyncio.Queue()
        self._responses = iter(responses)
        self._server: asyncio.Server | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("HTTP stub is not running")
        port = int(self._server.sockets[0].getsockname()[1])
        return f"http://127.0.0.1:{port}"

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line, headers = await _read_headers(reader)
            _method, path, _version = request_line.split(" ", maxsplit=2)
            payload = json.loads(await reader.readexactly(int(headers["content-length"])))
            if not isinstance(payload, Mapping):
                raise ValueError("HTTP payload must be an object")
            await self.requests.put(HttpRequest(path=path, payload=payload))
            response = next(self._responses)
            body = json.dumps(response).encode("utf-8")
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode("ascii")
                + body
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


async def _read_headers(reader: asyncio.StreamReader) -> tuple[str, dict[str, str]]:
    header = await reader.readuntil(b"\r\n\r\n")
    lines = header.decode("ascii").split("\r\n")
    headers = {
        name.casefold(): value.strip()
        for line in lines[1:]
        if line
        for name, value in (line.split(":", maxsplit=1),)
    }
    return lines[0], headers


async def _post_onebot_group_message(port: int) -> int:
    payload = {
        "time": 1_720_000_000,
        "self_id": 42,
        "post_type": "message",
        "sub_type": "normal",
        "user_id": 1001,
        "message_type": "group",
        "message_id": 7,
        "message": [{"type": "text", "data": {"text": "search Liteyuki"}}],
        "sender": {"user_id": 1001, "nickname": "tester"},
        "group_id": 2002,
    }
    body = json.dumps(payload).encode("utf-8")
    deadline = asyncio.get_running_loop().time() + 10
    while True:
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            break
        except ConnectionRefusedError:
            if asyncio.get_running_loop().time() >= deadline:
                raise
            await asyncio.sleep(0.01)
    try:
        writer.write(
            b"POST /onebot/v11/http HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"X-Self-ID: 42\r\n"
            b"Authorization: Bearer test-token\r\n"
            + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode("ascii")
            + body
        )
        await writer.drain()
        return int((await reader.readline()).decode("ascii").split(" ", maxsplit=2)[1])
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.asyncio
async def test_beta1_onebot_to_native_agent_tool_and_reply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _HttpStub(
        (
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {"name": "docs.search", "arguments": '{"query":"Liteyuki"}'},
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"role": "assistant", "content": "Liteyuki documentation found."}}]},
        )
    )
    onebot_api = _HttpStub(({"status": "ok", "retcode": 0, "data": {"message_id": 12345}},))
    await provider.start()
    await onebot_api.start()
    event_port = _unused_port()
    tool_calls: list[tuple[str, Mapping[str, object]]] = []

    async def search(event: EventEnvelope, arguments: Mapping[str, object]) -> AgentToolResult:
        tool_calls.append((event.id, arguments))
        return AgentToolResult(ok=True, data={"result": "Liteyuki documentation"})

    tool = AgentTool(
        id="docs.search",
        module_id="docs",
        title="Search docs",
        description="Search Liteyuki documentation.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=search,
        required_capabilities=frozenset({"docs.search"}),
    )

    def discover(permissions: object | None = None) -> ToolBroker:
        return ToolBroker({tool.id: tool}, permissions)  # type: ignore[arg-type]

    agent_plugin = importlib.import_module("liteyukibot_agent.plugin")
    monkeypatch.setattr(agent_plugin.ToolBroker, "discover", discover)
    app = LiteyukiApp(
        AppSettings(
            core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
            agent=AgentSettings(enabled=True, agent_harness="native"),
            plugins=PluginSettings(
                enabled=("liteyukibot.permissions", "liteyukibot.agent"),
                config={
                    "liteyukibot.permissions": {
                        "grants": [
                            {
                                "runtime_id": "platform",
                                "bot_id": "42",
                                "actor_id": "1001",
                                "capabilities": ["docs.search"],
                            }
                        ]
                    }
                },
            ),
            runtimes={
                "platform": RuntimeSettings(
                    kind="adapter",
                    ready_timeout_seconds=10,
                    options={
                        "adapters": {
                            "qq-main": {
                                "kind": "onebot-v11",
                                "bot_id": "42",
                                "config": {
                                    "event_host": "127.0.0.1",
                                    "event_port": event_port,
                                    "event_path": "/onebot/v11/http",
                                    "api_root": onebot_api.url,
                                    "access_token": "test-token",
                                },
                            }
                        }
                    },
                ),
                "agent": RuntimeSettings(
                    kind="agent",
                    ready_timeout_seconds=10,
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
                        "base_url": f"{provider.url}/v1",
                        "history_limit": 4,
                        "message_chunk_size": 100,
                        "max_concurrent_events": 1,
                        "model_timeout_seconds": 10,
                        "event_timeout_seconds": 15,
                    },
                ),
            },
        )
    )
    try:
        await app.start()
        assert await _post_onebot_group_message(event_port) == 204

        first_provider_request = await asyncio.wait_for(provider.requests.get(), timeout=15)
        second_provider_request = await asyncio.wait_for(provider.requests.get(), timeout=15)
        action = await asyncio.wait_for(onebot_api.requests.get(), timeout=15)
    finally:
        await app.stop()
        await provider.close()
        await onebot_api.close()

    assert len(tool_calls) == 1
    assert tool_calls[0][1] == {"query": "Liteyuki"}
    assert first_provider_request.path == "/v1/chat/completions"
    assert first_provider_request.payload["tools"] != []
    assert second_provider_request.path == "/v1/chat/completions"
    assert action.path == "/send_group_msg"
    assert action.payload == {
        "group_id": 2002,
        "message": [{"type": "text", "data": {"text": "Liteyuki documentation found."}}],
    }
