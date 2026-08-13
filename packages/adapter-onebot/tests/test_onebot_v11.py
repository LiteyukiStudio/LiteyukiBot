from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest
from liteyukibot_adapter_onebot.v11 import OneBotV11Connection, OneBotV11Error
from liteyukibot_adapter_onebot.v12 import OneBotV12Connection
from liteyukibot_runtime_adapter.contracts import AdapterContext
from websockets.asyncio.client import connect
from websockets.asyncio.server import ServerConnection, serve

from liteyukibot.events import ActionEnvelope, ConversationRef, EventEnvelope, Message, Segment, SendMessage
from liteyukibot.runtime.protocol import JsonValue


@dataclass(frozen=True, slots=True)
class ApiRequest:
    path: str
    headers: Mapping[str, str]
    payload: Mapping[str, Any]


class ApiStub:
    def __init__(
        self,
        *,
        status: int = 200,
        response: Mapping[str, Any] | None = None,
    ) -> None:
        self.requests: asyncio.Queue[ApiRequest] = asyncio.Queue()
        self._server: asyncio.Server | None = None
        self._status = status
        self._response = response or {"status": "ok", "retcode": 0, "data": {"message_id": 123}}

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("API stub is not running")
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
            method, path, headers, body = await _read_request(reader)
            if method != "POST":
                raise ValueError("expected POST")
            payload = json.loads(body)
            if not isinstance(payload, Mapping):
                raise ValueError("expected JSON object")
            await self.requests.put(ApiRequest(path=path, headers=headers, payload=payload))
            response = json.dumps(self._response).encode()
            writer.write(
                f"HTTP/1.1 {self._status} Stub\r\n".encode()
                + b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(response)}\r\n".encode()
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


def _context(port: int, api_root: str, token: str | None = "event-token") -> AdapterContext:
    config: dict[str, JsonValue] = {
        "event_host": "127.0.0.1",
        "event_port": port,
        "event_path": "/onebot/v11/http",
        "api_root": api_root,
    }
    if token is not None:
        config["access_token"] = token
    return AdapterContext("platform", "qq-main", "onebot-v11", "42", config)


def _event(text: str = "/help") -> dict[str, Any]:
    return {
        "time": 1_720_000_000,
        "self_id": 42,
        "post_type": "message",
        "sub_type": "normal",
        "user_id": 1001,
        "message_type": "group",
        "message_id": 7,
        "message": [{"type": "text", "data": {"text": text}}],
        "sender": {"user_id": 1001, "nickname": "tester", "card": "group tester"},
        "group_id": 2002,
    }


async def _post_event(
    port: int,
    event: Mapping[str, Any] | bytes,
    *,
    token: str | None = "event-token",
    self_id: str = "42",
    path: str = "/onebot/v11/http",
    content_type: str = "application/json",
) -> int:
    body = event if isinstance(event, bytes) else json.dumps(event).encode()
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        headers = [
            f"POST {path} HTTP/1.1",
            "Host: 127.0.0.1",
            f"Content-Type: {content_type}",
            f"X-Self-ID: {self_id}",
            f"Content-Length: {len(body)}",
            "Connection: close",
        ]
        if token is not None:
            headers.append(f"Authorization: Bearer {token}")
        writer.write("\r\n".join(headers).encode() + b"\r\n\r\n" + body)
        await writer.drain()
        return int((await reader.readline()).decode().split(" ", maxsplit=2)[1])
    finally:
        writer.close()
        await writer.wait_closed()


async def _read_request(reader: asyncio.StreamReader) -> tuple[str, str, dict[str, str], bytes]:
    method, path, _version = (await reader.readline()).decode().rstrip("\r\n").split(" ", maxsplit=2)
    headers: dict[str, str] = {}
    while line := await reader.readline():
        if line == b"\r\n":
            break
        name, value = line.decode().rstrip("\r\n").split(":", maxsplit=1)
        headers[name.lower()] = value.strip()
    return method, path, headers, await reader.readexactly(int(headers["content-length"]))


@pytest.mark.asyncio
async def test_v11_http_event_and_reply_action_round_trip() -> None:
    api = ApiStub()
    await api.start()
    connection = OneBotV11Connection(_context(_unused_port(), api.url))
    events: list[EventEnvelope] = []

    async def emit(event: EventEnvelope) -> None:
        events.append(event)

    try:
        await connection.start(emit)
        port = int(connection._server.sockets[0].getsockname()[1])  # type: ignore[union-attr]
        assert await _post_event(port, _event()) == 204
        assert len(events) == 1
        event = events[0]
        assert event.type == "message.group.normal"
        assert event.message == Message(segments=(Segment(type="text", data={"text": "/help"}),))
        assert event.conversation == ConversationRef(id="2002", type="group")

        response = await connection.execute(
            ActionEnvelope(
                runtime_id="platform",
                bot_id="42",
                action=SendMessage(
                    reply_token=event.reply_token,
                    message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
                ),
            )
        )
        request = await asyncio.wait_for(api.requests.get(), timeout=1)
        assert response == {"message_id": 123}
        assert request.path == "/send_group_msg"
        assert request.headers["authorization"] == "Bearer event-token"
        assert request.payload == {
            "group_id": 2002,
            "message": [{"type": "text", "data": {"text": "hello"}}],
        }
    finally:
        await connection.close()
        await api.close()


@pytest.mark.asyncio
async def test_v11_rejects_unauthorized_and_mismatched_callbacks() -> None:
    connection = OneBotV11Connection(_context(_unused_port(), "http://127.0.0.1:5701"))

    async def emit(_event: EventEnvelope) -> None:
        return None

    try:
        await connection.start(emit)
        port = int(connection._server.sockets[0].getsockname()[1])  # type: ignore[union-attr]
        assert await _post_event(port, _event(), token=None) == 401
        assert await _post_event(port, _event(), self_id="41") == 400
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_v11_maps_invalid_callback_requests_to_http_errors() -> None:
    connection = OneBotV11Connection(_context(_unused_port(), "http://127.0.0.1:5701"))

    async def emit(_event: EventEnvelope) -> None:
        return None

    try:
        await connection.start(emit)
        port = int(connection._server.sockets[0].getsockname()[1])  # type: ignore[union-attr]
        assert await _post_event(port, _event(), path="/unexpected") == 404
        assert await _post_event(port, _event(), content_type="text/plain") == 415
        assert await _post_event(port, b"{") == 400
    finally:
        await connection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "response", "message"),
    [
        (200, {"status": "failed", "retcode": 100, "wording": "denied"}, "denied"),
        (502, {"status": "ok", "retcode": 0, "data": {}}, "HTTP 502"),
    ],
)
async def test_v11_maps_api_failures_to_stable_errors(
    status: int,
    response: Mapping[str, Any],
    message: str,
) -> None:
    api = ApiStub(status=status, response=response)
    await api.start()
    connection = OneBotV11Connection(_context(_unused_port(), api.url))
    try:
        with pytest.raises(OneBotV11Error, match=message):
            await connection.execute(
                ActionEnvelope(
                    runtime_id="platform",
                    bot_id="42",
                    action=SendMessage(
                        conversation=ConversationRef(id="2002", type="group"),
                        message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
                    ),
                )
            )
        assert (await asyncio.wait_for(api.requests.get(), timeout=1)).path == "/send_group_msg"
    finally:
        await connection.close()
        await api.close()


@pytest.mark.asyncio
async def test_v11_accepts_but_ignores_non_message_events() -> None:
    connection = OneBotV11Connection(_context(_unused_port(), "http://127.0.0.1:5701"))
    events: list[EventEnvelope] = []

    async def emit(event: EventEnvelope) -> None:
        events.append(event)

    try:
        await connection.start(emit)
        port = int(connection._server.sockets[0].getsockname()[1])  # type: ignore[union-attr]
        assert await _post_event(port, {"self_id": 42, "post_type": "meta_event"}) == 204
        assert events == []
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_v11_listener_restarts_without_retaining_reply_routes() -> None:
    api = ApiStub()
    await api.start()
    port = _unused_port()
    connection = OneBotV11Connection(_context(port, api.url))
    events: list[EventEnvelope] = []

    async def emit(event: EventEnvelope) -> None:
        events.append(event)

    def reply_action(reply_token: str) -> ActionEnvelope:
        return ActionEnvelope(
            runtime_id="platform",
            bot_id="42",
            action=SendMessage(
                reply_token=reply_token,
                message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
            ),
        )

    try:
        await connection.start(emit)
        assert await _post_event(port, _event()) == 204
        first_token = events[0].reply_token
        assert first_token is not None
        await connection.close()

        await connection.start(emit)
        with pytest.raises(OneBotV11Error, match="unknown or expired"):
            await connection.execute(reply_action(first_token))
        assert await _post_event(port, _event("after restart")) == 204
        assert events[-1].message == Message(segments=(Segment(type="text", data={"text": "after restart"}),))
        assert events[-1].reply_token is not None
        assert await connection.execute(reply_action(events[-1].reply_token)) == {"message_id": 123}
        assert (await asyncio.wait_for(api.requests.get(), timeout=1)).path == "/send_group_msg"
    finally:
        await connection.close()
        await api.close()


def test_v11_non_loopback_listener_requires_token() -> None:
    context = AdapterContext(
        "platform",
        "qq-main",
        "onebot-v11",
        "42",
        {"event_host": "0.0.0.0", "event_port": 5700, "api_root": "http://127.0.0.1:5701"},
    )
    with pytest.raises(OneBotV11Error, match="require access_token"):
        OneBotV11Connection(context)


@pytest.mark.asyncio
async def test_v12_http_event_and_group_action_round_trip() -> None:
    api = ApiStub(response={"status": "ok", "retcode": 0, "data": {"message_id": "v12-1"}})
    await api.start()
    port = _unused_port()
    context = AdapterContext(
        "platform",
        "qq-v12",
        "onebot-v12",
        "42",
        {
            "event_host": "127.0.0.1",
            "event_port": port,
            "event_path": "/onebot/v12/http",
            "api_root": api.url,
            "access_token": "event-token",
        },
    )
    connection = OneBotV12Connection(context)
    events: list[EventEnvelope] = []

    async def emit(event: EventEnvelope) -> None:
        events.append(event)

    payload = {
        "id": "event-v12",
        "time": 1_720_000_000,
        "self_id": "42",
        "type": "message",
        "detail_type": "group",
        "group_id": "2002",
        "user_id": "1001",
        "message": [{"type": "text", "data": {"text": "hello"}}],
    }
    try:
        await connection.start(emit)
        assert await _post_event(port, payload, path="/onebot/v12/http") == 204
        assert events[0].adapter == "onebot-v12"
        assert events[0].conversation == ConversationRef(id="2002", type="group")
        assert await connection.execute(
            ActionEnvelope(
                runtime_id="platform",
                bot_id="42",
                action=SendMessage(
                    conversation=ConversationRef(id="2002", type="group"),
                    message=Message(segments=(Segment(type="text", data={"text": "reply"}),)),
                ),
            )
        ) == {"message_id": "v12-1"}
        request = await asyncio.wait_for(api.requests.get(), timeout=1)
        assert request.path == "/send_message"
        assert request.payload["detail_type"] == "group"
        assert request.payload["group_id"] == "2002"
    finally:
        await connection.close()
        await api.close()


@pytest.mark.asyncio
async def test_v11_forward_websocket_event_and_action_round_trip() -> None:
    incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def gateway(connection: ServerConnection) -> None:
        await connection.send(json.dumps(_event("from websocket")))
        request = json.loads(await connection.recv())
        await incoming.put(request)
        await connection.send(
            json.dumps({"status": "ok", "retcode": 0, "data": {"message_id": 99}, "echo": request["echo"]})
        )

    server = await serve(gateway, "127.0.0.1", 0)
    url = f"ws://127.0.0.1:{next(iter(server.sockets)).getsockname()[1]}/onebot"
    context = _context(_unused_port(), "http://127.0.0.1:5701")
    context = AdapterContext(
        context.runtime_id,
        context.instance_id,
        context.kind,
        context.bot_id,
        {**context.config, "transport": "forward_websocket", "ws_url": url},
    )
    connection = OneBotV11Connection(context)
    events: list[EventEnvelope] = []

    async def emit(event: EventEnvelope) -> None:
        events.append(event)

    try:
        await connection.start(emit)
        for _ in range(20):
            if events:
                break
            await asyncio.sleep(0.01)
        assert events[0].message == Message(segments=(Segment(type="text", data={"text": "from websocket"}),))
        assert await connection.execute(
            ActionEnvelope(
                runtime_id="platform",
                bot_id="42",
                action=SendMessage(
                    conversation=ConversationRef(id="2002", type="group"),
                    message=Message(segments=(Segment(type="text", data={"text": "reply"}),)),
                ),
            )
        ) == {"message_id": 99}
        assert (await asyncio.wait_for(incoming.get(), timeout=1))["action"] == "send_group_msg"
    finally:
        await connection.close()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_v12_reverse_websocket_event_and_action_round_trip() -> None:
    port = _unused_port()
    connection = OneBotV12Connection(
        AdapterContext(
            "platform",
            "qq-v12",
            "onebot-v12",
            "42",
            {
                "transport": "reverse_websocket",
                "ws_host": "127.0.0.1",
                "ws_port": port,
                "ws_path": "/onebot/v12/ws",
                "access_token": "event-token",
                "api_root": "http://127.0.0.1:5702",
            },
        )
    )
    events: list[EventEnvelope] = []

    async def emit(event: EventEnvelope) -> None:
        events.append(event)

    try:
        await connection.start(emit)
        async with connect(
            f"ws://127.0.0.1:{port}/onebot/v12/ws",
            additional_headers={"Authorization": "Bearer event-token"},
        ) as gateway:
            await gateway.send(
                json.dumps(
                    {
                        "self_id": "42",
                        "type": "message",
                        "detail_type": "group",
                        "group_id": "2002",
                        "user_id": "1001",
                        "message": [{"type": "text", "data": {"text": "reverse websocket"}}],
                    }
                )
            )
            for _ in range(20):
                if events:
                    break
                await asyncio.sleep(0.01)
            assert events[0].message is not None
            assert events[0].message.plain_text == "reverse websocket"
            action = asyncio.create_task(
                connection.execute(
                    ActionEnvelope(
                        runtime_id="platform",
                        bot_id="42",
                        action=SendMessage(
                            conversation=ConversationRef(id="2002", type="group"),
                            message=Message(
                                segments=(
                                    Segment(type="mention", data={"user_id": "1001"}),
                                    Segment(type="text", data={"text": "reply"}),
                                )
                            ),
                        ),
                    )
                )
            )
            request = json.loads(await gateway.recv())
            assert request["action"] == "send_message"
            assert request["params"]["message"] == [
                {"type": "mention", "data": {"user_id": "1001"}},
                {"type": "text", "data": {"text": "reply"}},
            ]
            await gateway.send(
                json.dumps({"status": "ok", "retcode": 0, "data": {"message_id": "reverse-1"}, "echo": request["echo"]})
            )
            assert await action == {"message_id": "reverse-1"}
    finally:
        await connection.close()
