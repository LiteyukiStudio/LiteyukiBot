from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest
from liteyukibot_adapter_satori.connection import SatoriConnection
from liteyukibot_runtime_adapter.contracts import AdapterContext
from websockets.asyncio.server import Server, ServerConnection, serve

from liteyukibot.events import (
    ActionEnvelope,
    ConversationRef,
    EditMessage,
    EventEnvelope,
    Message,
    Segment,
    SendMessage,
)


@dataclass(frozen=True, slots=True)
class ApiRequest:
    path: str
    payload: Mapping[str, Any]


class SatoriStub:
    def __init__(self) -> None:
        self.gateway: Server | None = None
        self.api: asyncio.Server | None = None
        self.identify: asyncio.Future[dict[str, Any]] | None = None
        self.requests: asyncio.Queue[ApiRequest] = asyncio.Queue()

    @property
    def gateway_url(self) -> str:
        assert self.gateway is not None
        return f"ws://127.0.0.1:{next(iter(self.gateway.sockets)).getsockname()[1]}/v1/events"

    @property
    def api_root(self) -> str:
        assert self.api is not None
        return f"http://127.0.0.1:{next(iter(self.api.sockets)).getsockname()[1]}/v1"

    async def start(self) -> None:
        self.identify = asyncio.get_running_loop().create_future()
        self.gateway = await serve(self._gateway, "127.0.0.1", 0)
        self.api = await asyncio.start_server(self._api, "127.0.0.1", 0)

    async def close(self) -> None:
        if self.gateway is not None:
            self.gateway.close()
            await self.gateway.wait_closed()
            self.gateway = None
        if self.api is not None:
            self.api.close()
            await self.api.wait_closed()
            self.api = None

    async def _gateway(self, connection: ServerConnection) -> None:
        raw = await connection.recv()
        assert isinstance(raw, str)
        assert self.identify is not None
        self.identify.set_result(json.loads(raw))
        await connection.send(json.dumps({"op": 4, "body": {"logins": []}}))
        await connection.send(
            json.dumps(
                {
                    "op": 0,
                    "body": {
                        "sn": 4,
                        "type": "message-created",
                        "self_id": "discord:bot",
                        "platform": "discord",
                        "timestamp": 1_720_000_000_000,
                        "channel": {"id": "channel-1", "type": 0, "guild_id": "guild-1"},
                        "user": {"id": "user-1", "name": "Tester"},
                        "message": {"id": "message-1", "content": 'hello <at id="user-2"/>'},
                    },
                }
            )
        )
        await connection.wait_closed()

    async def _api(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            method, path, _version = (await reader.readline()).decode().rstrip("\r\n").split(" ", maxsplit=2)
            assert method == "POST"
            headers: dict[str, str] = {}
            while line := await reader.readline():
                if line == b"\r\n":
                    break
                name, value = line.decode().rstrip("\r\n").split(":", maxsplit=1)
                headers[name.lower()] = value.strip()
            payload = json.loads(await reader.readexactly(int(headers["content-length"])))
            assert isinstance(payload, Mapping)
            await self.requests.put(ApiRequest(path, payload))
            response = b'{"id":"sent-1"}'
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                + f"Content-Length: {len(response)}\r\n".encode()
                + b"Connection: close\r\n\r\n"
                + response
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.mark.asyncio
async def test_satori_gateway_event_send_and_edit_round_trip() -> None:
    stub = SatoriStub()
    await stub.start()
    connection = SatoriConnection(
        AdapterContext(
            "platform",
            "satori-main",
            "satori",
            "discord:bot",
            {"gateway_url": stub.gateway_url, "api_root": stub.api_root, "access_token": "test-token"},
        )
    )
    events: list[EventEnvelope] = []

    async def emit(event: EventEnvelope) -> None:
        events.append(event)

    try:
        await connection.start(emit)
        assert stub.identify is not None
        assert await asyncio.wait_for(stub.identify, timeout=1) == {
            "op": 3,
            "body": {"token": "test-token", "sn": None},
        }
        for _ in range(20):
            if events:
                break
            await asyncio.sleep(0.01)
        assert len(events) == 1
        event = events[0]
        assert event.adapter == "satori"
        assert event.conversation == ConversationRef(id="channel-1", type="channel", parent_id="guild-1")
        assert event.message is not None
        assert event.message.plain_text == "hello "

        message = Message(segments=(Segment(type="text", data={"text": "reply"}),))
        assert await connection.execute(
            ActionEnvelope(
                runtime_id="platform",
                bot_id="discord:bot",
                action=SendMessage(conversation=event.conversation, message=message),
            )
        ) == {"id": "sent-1"}
        assert (await asyncio.wait_for(stub.requests.get(), timeout=1)) == ApiRequest(
            "/v1/message.create", {"channel_id": "channel-1", "content": "reply"}
        )

        assert await connection.execute(
            ActionEnvelope(
                runtime_id="platform",
                bot_id="discord:bot",
                action=EditMessage(message_id="sent-1", conversation=event.conversation, message=message),
            )
        ) == {"id": "sent-1"}
        assert (await asyncio.wait_for(stub.requests.get(), timeout=1)) == ApiRequest(
            "/v1/message.update", {"channel_id": "channel-1", "message_id": "sent-1", "content": "reply"}
        )
    finally:
        await connection.close()
        await stub.close()
