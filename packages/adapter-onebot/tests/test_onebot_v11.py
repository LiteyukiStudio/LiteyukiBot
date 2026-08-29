from __future__ import annotations

import asyncio
import json
import math
from typing import Any, cast

import liteyukibot_adapter_onebot.onebot.v11.snowluma.client as client_module
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from liteyukibot_adapter_onebot.onebot.v11 import (
    OneBotService,
    OneBotV11Error,
    SnowLumaAccountSettings,
    normalize_event,
    to_onebot_message,
    to_portable_message,
)
from liteyukibot_adapter_onebot.onebot.v11.snowluma.client import SnowLumaClient, SnowLumaConnectionError
from liteyukibot_kernel import (
    ActionEnvelope,
    AdapterAction,
    ConversationRef,
    DeleteMessage,
    DispatchResult,
    Message,
    RespondRequest,
    Segment,
    SendMessage,
)
from websockets.asyncio.server import Server, ServerConnection, serve

_JSON_SCALARS = st.none() | st.booleans() | st.integers() | st.text(max_size=32)
_ADAPTER_DATA = st.dictionaries(st.text(min_size=1, max_size=12), _JSON_SCALARS, max_size=5)
_ADAPTER_TYPES = st.from_regex(r"[A-Za-z][A-Za-z0-9_]{0,15}", fullmatch=True).filter(
    lambda value: value not in {"at", "face", "file", "image", "record", "reply", "text", "video"}
)


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


def test_onebot_v11_wire_message_conversion_supports_portable_and_adapter_segments() -> None:
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
    extended = to_portable_message(
        [
            {"type": "face", "data": {"id": "1"}},
            {"type": "record", "data": {"file": "voice.amr"}},
            {
                "type": "video",
                "data": {"file": "video-token", "url": "https://example.invalid/video.mp4"},
            },
            {"type": "file", "data": {"file_id": "file-token", "name": "report.txt"}},
            {"type": "json", "data": {"data": '{"kind":"card"}'}},
        ]
    )
    assert extended.segments == (
        Segment(type="emoji", data={"id": "1"}),
        Segment(type="audio", data={"file_id": "voice.amr"}),
        Segment(
            type="video",
            data={"file_id": "video-token", "url": "https://example.invalid/video.mp4"},
        ),
        Segment(type="file", data={"file_id": "file-token", "name": "report.txt"}),
        Segment(
            type="adapter",
            data={"adapter": "onebot.v11", "type": "json", "data": {"data": '{"kind":"card"}'}},
        ),
    )
    assert to_onebot_message(extended) == [
        {"type": "face", "data": {"id": "1"}},
        {"type": "record", "data": {"file": "voice.amr"}},
        {"type": "video", "data": {"file": "video-token"}},
        {"type": "file", "data": {"name": "report.txt", "file": "file-token"}},
        {"type": "json", "data": {"data": '{"kind":"card"}'}},
    ]


def test_onebot_v11_cq_string_conversion_supports_extension_segments() -> None:
    message = to_portable_message(
        "before &#91;literal&#93; &amp; [CQ:at,qq=1002] [CQ:reply,id=6] "
        "[CQ:image,file=https://example.invalid/a&#44;b.png] after"
    )
    assert message.segments == (
        Segment(type="text", data={"text": "before [literal] & "}),
        Segment(type="mention", data={"user_id": "1002"}),
        Segment(type="text", data={"text": " "}),
        Segment(type="reply", data={"message_id": "6"}),
        Segment(type="text", data={"text": " "}),
        Segment(type="image", data={"url": "https://example.invalid/a,b.png"}),
        Segment(type="text", data={"text": " after"}),
    )
    assert to_portable_message("hello [CQ:face,id=1] [CQ:json,data={&amp;quot;x&amp;quot;:1}]").segments == (
        Segment(type="text", data={"text": "hello "}),
        Segment(type="emoji", data={"id": "1"}),
        Segment(type="text", data={"text": " "}),
        Segment(
            type="adapter",
            data={"adapter": "onebot.v11", "type": "json", "data": {"data": '{&quot;x&quot;:1}'}},
        ),
    )


@settings(max_examples=100, deadline=None)
@given(_ADAPTER_TYPES, _ADAPTER_DATA)
def test_onebot_v11_unknown_segments_round_trip_without_data_loss(
    native_type: str,
    data: dict[str, object],
) -> None:
    wire = [{"type": native_type, "data": data}]
    assert to_onebot_message(to_portable_message(wire)) == wire


@settings(max_examples=100, deadline=None)
@given(st.text(max_size=80))
def test_onebot_v11_cq_text_entities_round_trip(value: str) -> None:
    encoded = value.replace("&", "&amp;").replace("[", "&#91;").replace("]", "&#93;").replace(",", "&#44;")
    assert to_portable_message(encoded).plain_text == value


def test_onebot_v11_event_filter_accepts_messages_notices_and_requests() -> None:
    assert normalize_event({"post_type": "message_sent"}, self_id="42") is None
    assert normalize_event({"post_type": "meta_event"}, self_id="42") is None
    assert normalize_event({"post_type": ["message"]}, self_id="42") is None
    assert normalize_event({**_event(message_type="channel"), "group_id": 2002}, self_id="42") is None
    event = normalize_event(_event(), self_id="42")
    assert event is not None
    assert event.adapter == "onebot.v11"
    assert event.type == "message.group.normal"
    assert event.bot_id == "42"
    assert event.conversation == ConversationRef(id="2002", type="group")

    notice = normalize_event(
        {
            "time": 1_720_000_001,
            "self_id": 42,
            "post_type": "notice",
            "notice_type": "group_increase",
            "sub_type": "invite",
            "group_id": 2002,
            "operator_id": 1002,
            "user_id": 1003,
        },
        self_id="42",
    )
    assert notice is not None
    assert notice.type == "notice.group_increase.invite"
    assert notice.conversation == ConversationRef(id="2002", type="group")
    assert notice.actor is not None and notice.actor.id == "1002"
    assert notice.details["user_id"] == "1003"

    request = normalize_event(
        {
            "time": 1_720_000_002,
            "self_id": 42,
            "post_type": "request",
            "request_type": "friend",
            "user_id": 1004,
            "comment": "hello",
            "flag": "friend-request",
        },
        self_id="42",
    )
    assert request is not None
    assert request.type == "request.friend"
    assert request.conversation == ConversationRef(id="1004", type="private")
    assert request.details["flag"] == "friend-request"


def test_onebot_v11_account_notice_has_no_fake_conversation() -> None:
    event = normalize_event(
        {
            "time": 1_720_000_003,
            "self_id": 42,
            "post_type": "notice",
            "notice_type": "bot_offline",
            "user_id": 42,
            "tag": "network",
            "message": "offline",
        },
        self_id="42",
    )
    assert event is not None
    assert event.conversation is None
    assert event.ordering_key == ("onebot", "42", "account")


def test_onebot_v11_normalizes_group_temporary_private_sessions() -> None:
    payload = _event(message_type="private")
    payload["sub_type"] = "group"
    payload["sender"]["group_id"] = 2002
    event = normalize_event(payload, self_id="42")
    assert event is not None
    assert event.conversation == ConversationRef(id="1001", type="private", parent_id="2002")


@pytest.mark.parametrize("timestamp", [None, True, "1720000000", math.inf, math.nan])
def test_onebot_v11_requires_a_valid_event_time(timestamp: Any) -> None:
    payload = _event()
    if timestamp is None:
        payload.pop("time")
    else:
        payload["time"] = timestamp
    with pytest.raises(OneBotV11Error, match="time"):
        normalize_event(payload, self_id="42")


def test_onebot_v11_wraps_non_json_event_values_as_adapter_errors() -> None:
    payload = _event()
    payload["extension"] = math.nan
    with pytest.raises(OneBotV11Error, match="invalid data"):
        normalize_event(payload, self_id="42")


@pytest.mark.asyncio
async def test_snowluma_routes_temporary_private_replies_to_the_source_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SnowLumaClient(_settings("ws://127.0.0.1:3001/"))
    captured: dict[str, Any] = {}

    async def call_api(api: str, params: Any) -> Any:
        captured["api"] = api
        captured["params"] = params
        return {"message_id": 99}

    monkeypatch.setattr(client, "call_api", call_api)
    action = SendMessage(
        conversation=ConversationRef(id="1001", type="private", parent_id="2002"),
        message=Message(segments=(Segment(type="text", data={"text": "reply"}),)),
    )

    assert await client.send_message(action) == {"message_id": 99}
    assert captured == {
        "api": "send_private_msg",
        "params": {
            "user_id": 1001,
            "group_id": 2002,
            "message": [{"type": "text", "data": {"text": "reply"}}],
        },
    }


@pytest.mark.asyncio
async def test_snowluma_executes_portable_and_extension_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SnowLumaClient(_settings("ws://127.0.0.1:3001/"))
    calls: list[tuple[str, Any]] = []

    async def call_api(api: str, params: Any) -> Any:
        calls.append((api, params))
        return None

    monkeypatch.setattr(client, "call_api", call_api)
    await client.delete_message(DeleteMessage(message_id="-7"))

    friend_request = normalize_event(
        {
            "time": 1_720_000_000,
            "self_id": 42,
            "post_type": "request",
            "request_type": "friend",
            "user_id": 1001,
            "flag": "friend-flag",
        },
        self_id="42",
    )
    assert friend_request is not None
    await client.respond_request(friend_request, RespondRequest(approve=True))

    group_request = normalize_event(
        {
            "time": 1_720_000_000,
            "self_id": 42,
            "post_type": "request",
            "request_type": "group",
            "sub_type": "invite",
            "group_id": 2002,
            "user_id": 1001,
            "flag": "group-flag",
        },
        self_id="42",
    )
    assert group_request is not None
    await client.respond_request(group_request, RespondRequest(approve=False, reason="not now"))
    await client.execute_adapter_action(
        AdapterAction(adapter="onebot.v11", name="get_group_info", params={"group_id": 2002})
    )

    assert calls == [
        ("delete_msg", {"message_id": -7}),
        ("set_friend_add_request", {"flag": "friend-flag", "approve": True}),
        (
            "set_group_add_request",
            {"flag": "group-flag", "sub_type": "invite", "approve": False, "reason": "not now"},
        ),
        ("get_group_info", {"group_id": 2002}),
    ]
    with pytest.raises(OneBotV11Error, match="portable kernel action"):
        await client.execute_adapter_action(
            AdapterAction(adapter="onebot.v11", name="delete_msg", params={"message_id": 7})
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("retcode", [False, 0.0])
async def test_snowluma_rejects_non_integer_success_retcode(retcode: Any) -> None:
    client = SnowLumaClient(_settings("ws://127.0.0.1:3001/"))
    connection = _Connection()
    client._connection = connection
    client._closed = False
    call = asyncio.create_task(client.call_api("send_group_msg", {"group_id": 2002, "message": []}))
    for _ in range(10):
        if connection.sent:
            break
        await asyncio.sleep(0)
    assert connection.sent
    request = json.loads(connection.sent[0])
    client._pending[request["echo"]].set_result(
        {"status": "ok", "retcode": retcode, "data": {}, "echo": request["echo"]}
    )
    with pytest.raises(OneBotV11Error, match="retcode"):
        await call
    await client.close()


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

    event = normalize_event(_event(), self_id="42", runtime_id="qq-main")
    assert event is not None
    cross_account = action.model_copy(update={"event_id": event.id, "runtime_id": event.runtime_id, "bot_id": "other"})
    result = await service.execute(event, cross_account)
    assert result.success is False
    assert result.error_code == "SOURCE_EVENT_MISMATCH"

    foreign_event = event.model_copy(update={"adapter": "other"})
    matching_action = action.model_copy(
        update={"event_id": foreign_event.id, "runtime_id": foreign_event.runtime_id, "bot_id": foreign_event.bot_id}
    )
    result = await service.execute(foreign_event, matching_action)
    assert result.success is False
    assert result.error_code == "SOURCE_EVENT_MISMATCH"


@pytest.mark.asyncio
async def test_onebot_service_executes_source_bound_request_and_adapter_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OneBotService(
        {"qq-main": _settings("ws://127.0.0.1:3001/", self_id="42", token=None)},
        event_bus=RecordingEventBus(),  # type: ignore[arg-type]
    )
    calls: list[tuple[str, Any]] = []

    async def call_api(api: str, params: Any) -> Any:
        calls.append((api, params))
        return {"ok": True}

    monkeypatch.setattr(service.accounts["qq-main"], "call_api", call_api)
    event = normalize_event(
        {
            "time": 1_720_000_000,
            "self_id": 42,
            "post_type": "request",
            "request_type": "group",
            "sub_type": "add",
            "group_id": 2002,
            "user_id": 1001,
            "flag": "request-flag",
        },
        self_id="42",
        runtime_id="qq-main",
    )
    assert event is not None
    request_action = ActionEnvelope(
        event_id=event.id,
        runtime_id=event.runtime_id,
        bot_id=event.bot_id,
        action=RespondRequest(approve=True),
    )
    assert (await service.execute(event, request_action)).success is True

    adapter_action = request_action.model_copy(
        update={
            "action_id": "adapter-action",
            "action": AdapterAction(
                adapter="onebot.v11",
                name="get_group_info",
                params={"group_id": 2002},
            ),
        }
    )
    assert (await service.execute(event, adapter_action)).success is True
    assert calls == [
        (
            "set_group_add_request",
            {"flag": "request-flag", "sub_type": "add", "approve": True, "reason": ""},
        ),
        ("get_group_info", {"group_id": 2002}),
    ]

    wrong_adapter = adapter_action.model_copy(
        update={"action": AdapterAction(adapter="other", name="get_group_info")}
    )
    result = await service.execute(event, wrong_adapter)
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
    event = normalize_event(_event(), self_id="42", runtime_id="qq-main")
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
async def test_snowluma_close_cancellation_tracks_lifecycle_tasks() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def stuck() -> None:
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()

    client = SnowLumaClient(_settings("ws://127.0.0.1:3001/"))
    client._closed = False
    lifecycle = asyncio.create_task(stuck())
    client._task = lifecycle
    await started.wait()

    entered = asyncio.Event()
    original_cancel_tasks = client._cancel_tasks

    async def cancel_tasks(
        tasks: tuple[asyncio.Task[Any], ...],
        *,
        deadline: float,
    ) -> tuple[asyncio.Task[Any], ...]:
        entered.set()
        return await original_cancel_tasks(tasks, deadline=deadline)

    client._cancel_tasks = cancel_tasks  # type: ignore[method-assign]
    closing = asyncio.create_task(client.close(timeout_seconds=5))
    await entered.wait()
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing

    assert lifecycle in client._lingering_tasks
    with pytest.raises(RuntimeError, match="cleanup"):
        await client.start()

    release.set()
    await asyncio.wait_for(lifecycle, timeout=1)
    await asyncio.sleep(0)
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
