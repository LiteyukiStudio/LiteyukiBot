from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from liteyukibot_adapter_onebot.onebot.v11 import (
    OneBotService,
    OneBotV11Error,
    SnowLumaAccountSettings,
    normalize_event,
    to_onebot_message,
    to_portable_message,
)
from liteyukibot_kernel import ActionEnvelope, ConversationRef, Message, Segment, SendMessage
from websockets.asyncio.server import Server, ServerConnection, serve


class RecordingEventBus:
    def __init__(self) -> None:
        self.events: asyncio.Queue[Any] = asyncio.Queue()

    async def publish(self, event: Any) -> None:
        await self.events.put(event)


def _settings(url: str, *, self_id: str = "42", token: str | None = "secret") -> SnowLumaAccountSettings:
    return SnowLumaAccountSettings(
        implementation="snowluma",
        self_id=self_id,
        ws_url=url,
        access_token=token,
    )


def _event(*, message_type: str = "group", self_id: int = 42, message_id: int = 7) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "time": 1_720_000_000,
        "self_id": self_id,
        "post_type": "message",
        "sub_type": "normal",
        "user_id": 1001,
        "message_type": message_type,
        "message_id": message_id,
        "message": [
            {"type": "text", "data": {"text": "hello "}},
            {"type": "at", "data": {"qq": "1002"}},
            {"type": "reply", "data": {"id": 6}},
            {"type": "image", "data": {"file": "https://example.invalid/a.png"}},
        ],
        "sender": {"user_id": 1001, "nickname": "tester"},
    }
    if message_type == "group":
        payload["group_id"] = 2002
    return payload


def _port(server: Server) -> int:
    socket = next(iter(server.sockets))
    return int(socket.getsockname()[1])


def test_snowluma_account_settings_validate_transport_security() -> None:
    assert _settings("ws://127.0.0.1:3001/").ws_url == "ws://127.0.0.1:3001/"
    assert _settings("wss://gateway.example.test/", token=None).implementation == "snowluma"
    with pytest.raises(ValueError, match="loopback"):
        _settings("ws://gateway.example.test/")
    with pytest.raises(ValueError, match="literal"):
        SnowLumaAccountSettings(implementation="other", self_id="42", ws_url="ws://127.0.0.1:3001/")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="token"):
        _settings("ws://127.0.0.1:3001/", token=" ")


def test_onebot_v11_wire_message_conversion_is_limited_to_supported_segments() -> None:
    message = to_portable_message(_event()["message"])
    assert message.segments == (
        Segment(type="text", data={"text": "hello "}),
        Segment(type="mention", data={"user_id": "1002"}),
        Segment(type="reply", data={"message_id": "6"}),
        Segment(type="image", data={"url": "https://example.invalid/a.png"}),
    )
    assert to_onebot_message(message) == [
        {"type": "text", "data": {"text": "hello "}},
        {"type": "at", "data": {"qq": "1002"}},
        {"type": "reply", "data": {"id": "6"}},
        {"type": "image", "data": {"file": "https://example.invalid/a.png"}},
    ]
    with pytest.raises(OneBotV11Error, match="unsupported"):
        to_portable_message([{"type": "face", "data": {"id": "1"}}])


def test_onebot_v11_event_filter_accepts_only_private_and_group_messages() -> None:
    assert normalize_event({"post_type": "notice"}, self_id="42") is None
    assert normalize_event({"post_type": "message_sent"}, self_id="42") is None
    assert normalize_event({**_event(message_type="channel"), "group_id": 2002}, self_id="42") is None
    event = normalize_event(_event(), self_id="42")
    assert event is not None
    assert event.adapter == "onebot.v11"
    assert event.type == "message.group.normal"
    assert event.bot_id == "42"
    assert event.conversation == ConversationRef(id="2002", type="group")


@pytest.mark.asyncio
async def test_onebot_service_publishes_snowluma_events_and_sends_source_reply() -> None:
    received: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
    event_payload = _event()

    async def gateway(connection: ServerConnection) -> None:
        request = connection.request
        assert request is not None
        assert request.headers.get("Authorization") == "Bearer secret"
        await connection.send(json.dumps(event_payload))
        raw = await connection.recv()
        assert isinstance(raw, str)
        payload = json.loads(raw)
        received.set_result(payload)
        await connection.send(
            json.dumps({"status": "ok", "retcode": 0, "data": {"message_id": 99}, "echo": payload["echo"]})
        )
        await connection.wait_closed()

    server = await serve(gateway, "127.0.0.1", 0)
    bus = RecordingEventBus()
    service = OneBotService(
        {"qq-main": _settings(f"ws://127.0.0.1:{_port(server)}/onebot")},
        event_bus=bus,  # type: ignore[arg-type]
    )
    try:
        await service.start()
        event = await asyncio.wait_for(bus.events.get(), timeout=1)
        assert event.runtime_id == "qq-main"
        assert event.message.plain_text == "hello "
        assert event.reply_token is not None
        action = ActionEnvelope(
            event_id=event.id,
            runtime_id=event.runtime_id,
            bot_id=event.bot_id,
            action=SendMessage(
                conversation=None,
                reply_token=event.reply_token,
                message=Message(segments=(Segment(type="text", data={"text": "reply"}),)),
            ),
        )
        result = await service.execute(event, action)
        assert result.success is True
        assert result.data == {"message_id": 99}
        request = await asyncio.wait_for(received, timeout=1)
        assert request["action"] == "send_group_msg"
        assert request["params"] == {
            "group_id": 2002,
            "message": [{"type": "text", "data": {"text": "reply"}}],
        }
    finally:
        await service.close()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_onebot_service_rejects_proactive_and_cross_account_actions() -> None:
    service = OneBotService(
        {"qq-main": _settings("ws://127.0.0.1:3001/", self_id="42", token=None)},
        event_bus=RecordingEventBus(),  # type: ignore[arg-type]
    )
    action = ActionEnvelope(
        runtime_id="qq-main",
        bot_id="42",
        action=SendMessage(
            conversation=ConversationRef(id="2002", type="group"),
            message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
        ),
    )
    result = await service.execute(None, action)
    assert result.success is False
    assert result.error_code == "SOURCE_EVENT_REQUIRED"

    event = normalize_event(_event(), self_id="42", runtime_id="qq-main", adapter="onebot.v11.snowluma")
    assert event is not None
    cross_account = action.model_copy(update={"event_id": event.id, "runtime_id": event.runtime_id, "bot_id": "other"})
    result = await service.execute(event, cross_account)
    assert result.success is False
    assert result.error_code == "SOURCE_EVENT_MISMATCH"


@pytest.mark.asyncio
async def test_disconnect_fails_pending_call_and_clears_reply_routes() -> None:
    connected = asyncio.Event()
    close_connection: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def gateway(connection: ServerConnection) -> None:
        connected.set()
        await close_connection
        await connection.close()

    server = await serve(gateway, "127.0.0.1", 0)
    service = OneBotService(
        {"qq-main": _settings(f"ws://127.0.0.1:{_port(server)}/")},
        event_bus=RecordingEventBus(),  # type: ignore[arg-type]
    )
    try:
        await service.start()
        await asyncio.wait_for(connected.wait(), timeout=1)
        client = service.accounts["qq-main"]
        pending = asyncio.create_task(client.call_api("send_group_msg", {"group_id": 2002, "message": "pending"}))
        await asyncio.sleep(0)
        close_connection.set_result(None)
        with pytest.raises(OneBotV11Error):
            await asyncio.wait_for(pending, timeout=1)
        assert client.pending_count == 0
        assert client.reply_routes == {}
    finally:
        await service.close()
        server.close()
        await server.wait_closed()
