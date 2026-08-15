from __future__ import annotations

import asyncio
import importlib.util
import json
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from liteyukibot.app import LiteyukiApp
from liteyukibot.config import AppSettings, CoreSettings, PluginSettings, RuntimeSettings


def _module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False


pytestmark = pytest.mark.skipif(
    not _module_available("nonebot") or not _module_available("nonebot.adapters.onebot.v11"),
    reason="NoneBot OneBot v11 extras are not installed",
)


@dataclass(frozen=True, slots=True)
class OneBotApiRequest:
    path: str
    payload: Mapping[str, Any]


class OneBotApiStub:
    def __init__(self) -> None:
        self.requests: asyncio.Queue[OneBotApiRequest] = asyncio.Queue()
        self._server: asyncio.Server | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("OneBot API stub is not running")
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
            request_line = (await reader.readline()).decode("ascii").rstrip("\r\n")
            method, path, version = request_line.split(" ", maxsplit=2)
            if method != "POST" or version != "HTTP/1.1":
                raise ValueError("expected an HTTP/1.1 POST request")

            headers: dict[str, str] = {}
            while line := await reader.readline():
                if line == b"\r\n":
                    break
                name, value = line.decode("ascii").rstrip("\r\n").split(":", maxsplit=1)
                headers[name.lower()] = value.strip()
            content_length = int(headers["content-length"])
            payload = json.loads(await reader.readexactly(content_length))
            if not isinstance(payload, dict):
                raise ValueError("OneBot API payload must be an object")
            await self.requests.put(OneBotApiRequest(path=path, payload=payload))

            response = json.dumps(
                {"status": "ok", "retcode": 0, "data": {"message_id": 12345}}
            ).encode("utf-8")
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
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_handle:
        socket_handle.bind(("127.0.0.1", 0))
        return int(socket_handle.getsockname()[1])


async def _post_onebot_event(port: int, payload: Mapping[str, Any]) -> int:
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
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        status_line = (await reader.readline()).decode("ascii").rstrip("\r\n")
        return int(status_line.split(" ", maxsplit=2)[1])
    finally:
        writer.close()
        await writer.wait_closed()


async def _wait_for_event_bus_idle(app: LiteyukiApp) -> None:
    await asyncio.wait_for(app.events._idle.wait(), timeout=10)


def _group_help_event() -> dict[str, Any]:
    return {
        "time": 1_720_000_000,
        "self_id": 42,
        "post_type": "message",
        "sub_type": "normal",
        "user_id": 1001,
        "message_type": "group",
        "message_id": 7,
        "message": [{"type": "text", "data": {"text": "/help"}}],
        "raw_message": "/help",
        "font": 0,
        "sender": {"user_id": 1001, "nickname": "tester", "card": "group tester"},
        "group_id": 2002,
    }


@pytest.mark.asyncio
async def test_nonebot_onebot_v11_http_group_help_round_trip(tmp_path: Path) -> None:
    api = OneBotApiStub()
    await api.start()
    runtime_port = _unused_port()
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        plugins=PluginSettings(
            enabled=(
                "liteyukibot.permissions",
                "liteyukibot.commands",
                "liteyukibot.essentials",
            ),
            config={"liteyukibot.essentials": {"language": "en"}},
        ),
        runtimes={
            "nonebot": RuntimeSettings(
                kind="nonebot",
                ready_timeout_seconds=10,
                options={
                    "adapters": ("nonebot.adapters.onebot.v11:Adapter",),
                    "config": {
                        "driver": "~fastapi+~httpx",
                        "host": "127.0.0.1",
                        "port": runtime_port,
                        "onebot_api_roots": {"42": api.url},
                    },
                },
            )
        },
    )
    app = LiteyukiApp(settings)
    try:
        await app.start()
        assert await _post_onebot_event(runtime_port, _group_help_event()) == 204

        request = await asyncio.wait_for(api.requests.get(), timeout=10)
        assert request.path == "/send_msg"
        assert request.payload["group_id"] == 2002
        assert request.payload["message_type"] == "group"
        assert request.payload["message"] == [
            {
                "type": "text",
                "data": {"text": "Available commands:\n/help (/帮助) - Show available commands"},
            }
        ]
        await _wait_for_event_bus_idle(app)
        assert api.requests.empty()
    finally:
        await app.stop()
        await api.close()
