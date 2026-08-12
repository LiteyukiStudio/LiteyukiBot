from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from liteyukibot.app import LiteyukiApp
from liteyukibot.config import AppSettings, CoreSettings, PluginSettings, RuntimeSettings


@dataclass(frozen=True, slots=True)
class ApiRequest:
    path: str
    payload: Mapping[str, Any]


class ApiStub:
    def __init__(self) -> None:
        self.requests: asyncio.Queue[ApiRequest] = asyncio.Queue()
        self._server: asyncio.Server | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("OneBot API stub is not running")
        return f"http://127.0.0.1:{self._server.sockets[0].getsockname()[1]}"

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = (await reader.readline()).decode("ascii").rstrip("\r\n")
            method, path, _version = request_line.split(" ", maxsplit=2)
            if method != "POST":
                raise ValueError("expected an HTTP POST request")
            headers: dict[str, str] = {}
            while line := await reader.readline():
                if line == b"\r\n":
                    break
                name, value = line.decode("ascii").rstrip("\r\n").split(":", maxsplit=1)
                headers[name.lower()] = value.strip()
            payload = json.loads(await reader.readexactly(int(headers["content-length"])))
            if not isinstance(payload, Mapping):
                raise ValueError("OneBot API payload must be an object")
            await self.requests.put(ApiRequest(path=path, payload=payload))
            response = json.dumps({"status": "ok", "retcode": 0, "data": {"message_id": 12345}}).encode("utf-8")
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                + b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(response)}\r\n".encode("ascii")
                + b"Connection: close\r\n\r\n"
                + response
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


async def _post_onebot_event(port: int) -> int:
    payload = {
        "time": 1_720_000_000,
        "self_id": 42,
        "post_type": "message",
        "sub_type": "normal",
        "user_id": 1001,
        "message_type": "group",
        "message_id": 7,
        "message": [{"type": "text", "data": {"text": "/help"}}],
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
            + b"Host: 127.0.0.1\r\n"
            + b"Content-Type: application/json\r\n"
            + b"X-Self-ID: 42\r\n"
            + b"Authorization: Bearer test-token\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        return int((await reader.readline()).decode("ascii").split(" ", maxsplit=2)[1])
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.asyncio
async def test_adapter_runtime_onebot_v11_group_help_round_trip(tmp_path: Path) -> None:
    api = ApiStub()
    await api.start()
    event_port = _unused_port()
    app = LiteyukiApp(
        AppSettings(
            core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
            plugins=PluginSettings(
                enabled=("liteyukibot.permissions", "liteyukibot.commands", "liteyukibot.essentials"),
                config={"liteyukibot.essentials": {"language": "en"}},
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
                                    "api_root": api.url,
                                    "access_token": "test-token",
                                },
                            }
                        }
                    },
                )
            },
        )
    )
    try:
        await app.start()
        assert await _post_onebot_event(event_port) == 204
        request = await asyncio.wait_for(api.requests.get(), timeout=10)
        assert request.path == "/send_group_msg"
        assert request.payload == {
            "group_id": 2002,
            "message": [
                {"type": "text", "data": {"text": "Available commands:\n/help (/帮助) - Show available commands"}}
            ],
        }
    finally:
        await app.stop()
        await api.close()
