from __future__ import annotations

import asyncio
import json
import math
from typing import Any, cast

import liteyukibot_adapter_onebot.onebot.v11.snowluma.client as client_module
import pytest
from liteyukibot_adapter_onebot.onebot.v11 import (
    OneBotService,
    OneBotV11Error,
    SnowLumaAccountSettings,
    normalize_event,
    to_onebot_message,
    to_portable_message,
)
from liteyukibot_adapter_onebot.onebot.v11.snowluma.client import SnowLumaClient, SnowLumaConnectionError
from liteyukibot_kernel import ActionEnvelope, ConversationRef, DispatchResult, Message, Segment, SendMessage
from websockets.asyncio.server import Server, ServerConnection, serve


class RecordingEventBus:
    def __init__(self, *, status: str = "processed") -> None:
        self.events: asyncio.Queue[Any] = asyncio.Queue()
        self.status = status

    async def publish(self, event: Any) -> DispatchResult:
        await self.events.put(event)
        return DispatchResult(event_id=event.id, status=self.status)  # type: ignore[arg-type]


class _Connection:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        self.closed = True


class _UncooperativeSendConnection(_Connection):
    def __init__(self) -> None:
        super().__init__()
        self.send_started = asyncio.Event()
        self.release_send = asyncio.Event()
        self.closed_event = asyncio.Event()

    async def send(self, payload: str) -> None:
        self.send_started.set()
        try:
            await self.release_send.wait()
        except asyncio.CancelledError:
            await self.release_send.wait()
        self.sent.append(payload)

    async def close(self) -> None:
        self.closed = True
        self.closed_event.set()


class _RetryingCloseConnection(_Connection):
    def __init__(self) -> None:
        super().__init__()
        self.close_attempts = 0

    async def close(self) -> None:
        self.close_attempts += 1
        if self.close_attempts == 1:
            raise RuntimeError("transport close failed")
        self.closed = True


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
    with pytest.raises(ValueError, match="string"):
        SnowLumaAccountSettings(
            implementation="snowluma",
            self_id="42",
            ws_url="ws://127.0.0.1:3001/",
            access_token=cast(str | None, 123),
        )


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
        service_status = service.status()
        assert service_status["state"] == "ready"
        assert service_status["connected_accounts"] == 1
        assert service_status["accounts"]["qq-main"]["pending_calls"] == 0  # type: ignore[index]
        assert "secret" not in json.dumps(service_status)
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
async def test_onebot_service_does_not_return_remote_action_error_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OneBotService(
        {"qq-main": _settings("ws://127.0.0.1:3001/", self_id="42", token=None)},
        event_bus=RecordingEventBus(),  # type: ignore[arg-type]
    )
    event = normalize_event(_event(), self_id="42", runtime_id="qq-main", adapter="onebot.v11.snowluma")
    assert event is not None

    async def fail(_action: SendMessage) -> Any:
        raise OneBotV11Error("remote wording token=secret")

    monkeypatch.setattr(service.accounts["qq-main"], "send_message", fail)
    action = ActionEnvelope(
        event_id=event.id,
        runtime_id=event.runtime_id,
        bot_id=event.bot_id,
        action=SendMessage(
            conversation=event.conversation,
            message=Message(segments=(Segment(type="text", data={"text": "reply"}),)),
        ),
    )

    result = await service.execute(event, action)

    assert result.error_message == "OneBot action failed"
    assert "secret" not in str(result)
    await service.close()


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


@pytest.mark.asyncio
async def test_snowluma_does_not_reconnect_while_an_endpoint_is_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connected = asyncio.Event()
    connection_count = 0

    async def gateway(connection: ServerConnection) -> None:
        nonlocal connection_count
        connection_count += 1
        connected.set()
        await connection.wait_closed()

    server = await serve(gateway, "127.0.0.1", 0)
    monkeypatch.setattr(client_module, "CONNECT_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(client_module, "RECONNECT_DELAY_SECONDS", 0.01)
    client = SnowLumaClient(_settings(f"ws://127.0.0.1:{_port(server)}/"))
    try:
        await client.start()
        await asyncio.wait_for(connected.wait(), timeout=1)
        await asyncio.sleep(0.12)
        assert client._events.maxsize == client_module._EVENT_QUEUE_CAPACITY
        assert connection_count == 1
        assert client.connected
    finally:
        await client.close()
        server.close()
        await server.wait_closed()


def test_snowluma_bounds_retained_reply_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "_MAX_REPLY_ROUTES", 2)
    client = SnowLumaClient(_settings("ws://127.0.0.1:3001/"))
    conversation = ConversationRef(id="2002", type="group")

    client._remember_reply_route("first", conversation)
    client._remember_reply_route("second", conversation)
    client._remember_reply_route("third", conversation)

    assert tuple(client.reply_routes) == ("second", "third")


def test_snowluma_rejects_synchronous_event_handlers() -> None:
    with pytest.raises(TypeError, match="async callable"):
        SnowLumaClient(_settings("ws://127.0.0.1:3001/"), on_event=cast(Any, lambda _event: None))


@pytest.mark.asyncio
async def test_snowluma_rejects_non_finite_close_timeout() -> None:
    client = SnowLumaClient(_settings("ws://127.0.0.1:3001/"))
    for value in (math.inf, math.nan):
        with pytest.raises(ValueError, match="finite"):
            await client.close(timeout_seconds=value)


@pytest.mark.asyncio
async def test_snowluma_propagates_transport_close_failure_and_retries() -> None:
    client = SnowLumaClient(_settings("ws://127.0.0.1:3001/"))
    connection = _RetryingCloseConnection()
    client._connection = connection
    client._closed = False

    with pytest.raises(SnowLumaConnectionError, match="close failed"):
        await client.close(timeout_seconds=1)
    assert client.status()["state"] == "failed"
    assert client.status()["cleanup_error"] == "RuntimeError"

    await client.close(timeout_seconds=1)
    assert connection.close_attempts == 2
    assert connection.closed
    assert client.status()["state"] == "stopped"
    assert client.status()["cleanup_error"] is None


@pytest.mark.asyncio
async def test_snowluma_rejects_oversize_outbound_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "_MAX_MESSAGE_BYTES", 128)
    client = SnowLumaClient(_settings("ws://127.0.0.1:3001/"))
    connection = _Connection()
    client._connection = connection
    client._closed = False

    with pytest.raises(OneBotV11Error, match="maximum message size"):
        await client.call_api("send_group_msg", {"message": "x" * 256})
    assert connection.sent == []
    await client.close()


@pytest.mark.asyncio
async def test_snowluma_close_drains_queued_events() -> None:
    client = SnowLumaClient(_settings("ws://127.0.0.1:3001/"))
    event = normalize_event(_event(), self_id="42")
    assert event is not None
    client._closed = False
    reserved = await client._reserve_event(event)
    assert reserved is not None
    await client._events.put((event, *reserved))

    await client.close(timeout_seconds=1)

    assert client.status()["state"] == "stopped"
    assert client.status()["queued_events"] == 0
    assert client.status()["queued_event_bytes"] == 0
    assert client._event_slots._value == client_module._EVENT_QUEUE_BYTE_SLOTS


@pytest.mark.asyncio
async def test_snowluma_close_blocks_a_call_waiting_for_the_send_gate() -> None:
    client = SnowLumaClient(_settings("ws://127.0.0.1:3001/"))
    connection = _Connection()
    client._connection = connection
    client._closed = False
    await client._send_lock.acquire()
    call = asyncio.create_task(client.call_api("send_group_msg", {"group_id": 1, "message": []}))
    await asyncio.sleep(0)
    closing = asyncio.create_task(client.close(timeout_seconds=0.1))
    await asyncio.sleep(0)
    assert client._closing
    client._send_lock.release()
    with pytest.raises(OneBotV11Error, match="closed"):
        await call
    await closing
    assert connection.sent == []
    assert connection.closed


@pytest.mark.asyncio
async def test_snowluma_close_tracks_an_uncooperative_task() -> None:
    release = asyncio.Event()

    async def stuck() -> None:
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()

    client = SnowLumaClient(_settings("ws://127.0.0.1:3001/"))
    client._closed = False
    client._task = asyncio.create_task(stuck())
    await asyncio.sleep(0)

    await client.close(timeout_seconds=0.01)

    assert client.status()["state"] == "cleanup_pending"
    assert client.status()["background_tasks"] == 1
    release.set()
    await asyncio.sleep(0.02)
    assert client.status()["background_tasks"] == 0


@pytest.mark.asyncio
async def test_snowluma_close_defers_transport_close_behind_uncooperative_send() -> None:
    client = SnowLumaClient(_settings("ws://127.0.0.1:3001/"))
    connection = _UncooperativeSendConnection()
    client._connection = connection
    client._closed = False
    call = asyncio.create_task(client.call_api("send_group_msg", {"group_id": 1, "message": []}))
    await asyncio.wait_for(connection.send_started.wait(), timeout=1)

    await client.close(timeout_seconds=0.01)

    assert connection.closed is False
    assert cast(int, client.status()["background_tasks"]) >= 1
    connection.release_send.set()
    with pytest.raises(SnowLumaConnectionError):
        await call
    await asyncio.wait_for(connection.closed_event.wait(), timeout=1)
    assert len(connection.sent) == 1
    for _ in range(20):
        if cast(int, client.status()["background_tasks"]) == 0:
            break
        await asyncio.sleep(0.01)
    assert cast(int, client.status()["background_tasks"]) == 0


@pytest.mark.asyncio
async def test_onebot_service_reports_account_cleanup_with_lingering_tasks() -> None:
    release = asyncio.Event()

    async def stuck() -> None:
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()

    service = OneBotService(
        {"qq-main": _settings("ws://127.0.0.1:3001/")},
        close_timeout=0.01,
    )
    client = service.accounts["qq-main"]
    client._closed = False
    client._task = asyncio.create_task(stuck())
    with pytest.raises(BaseExceptionGroup, match="account cleanup failed"):
        await service.close()
    assert service.status()["state"] == "cleanup_pending"
    assert cast(int, service.status()["background_tasks"]) == 1
    release.set()
    for _ in range(20):
        if cast(int, service.status()["background_tasks"]) == 0:
            break
        await asyncio.sleep(0.01)
    assert cast(int, service.status()["background_tasks"]) == 0
