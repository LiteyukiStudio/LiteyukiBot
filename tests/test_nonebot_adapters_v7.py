from __future__ import annotations

import importlib
import importlib.util
import json
import math
from datetime import UTC, datetime
from typing import Any

import pytest

from liteyukibot.events import (
    ActionEnvelope,
    CallApi,
    ConversationRef,
    Message,
    Segment,
    SendMessage,
)
from liteyukibot.runtime.nonebot import NoneBotHost
from liteyukibot.runtime.nonebot_contracts import (
    AdapterContractError,
    adapter_id,
    json_value,
    normalize_event,
    to_native_message,
)

_ADAPTER_MODULES = (
    "nonebot.adapters.onebot.v11",
    "nonebot.adapters.onebot.v12",
    "nonebot.adapters.satori",
)
_ADAPTERS_INSTALLED = importlib.util.find_spec("nonebot") is not None and all(
    importlib.util.find_spec(module) is not None for module in _ADAPTER_MODULES
)
pytestmark = pytest.mark.skipif(
    not _ADAPTERS_INSTALLED,
    reason="NoneBot OneBot and Satori extras are not installed",
)


class FakeAdapter:
    def __init__(self, name: str) -> None:
        self.name = name

    def get_name(self) -> str:
        return self.name


class FakeBot:
    def __init__(self, self_id: str, adapter_name: str) -> None:
        self.self_id = self_id
        self.adapter = FakeAdapter(adapter_name)
        self.api_calls: list[tuple[str, dict[str, Any]]] = []
        self.replies: list[tuple[Any, Any]] = []
        self.channel_sends: list[tuple[str, Any]] = []
        self.api_result: Any = {"message_id": "sent"}

    async def call_api(self, api: str, **params: Any) -> Any:
        self.api_calls.append((api, params))
        return self.api_result

    async def send(self, event: Any, message: Any) -> Any:
        self.replies.append((event, message))
        return self.api_result

    async def send_message(self, channel_id: str, message: Any) -> Any:
        self.channel_sends.append((channel_id, message))
        return self.api_result


class FakeNoneBot:
    def __init__(self, *bots: FakeBot) -> None:
        self.bots = {bot.self_id: bot for bot in bots}

    def get_bot(self, bot_id: str) -> FakeBot:
        return self.bots[bot_id]


def _onebot_v11_group_event() -> Any:
    onebot = importlib.import_module("nonebot.adapters.onebot.v11")
    return onebot.GroupMessageEvent.model_validate(
        {
            "time": 1_720_000_000,
            "self_id": 42,
            "post_type": "message",
            "sub_type": "normal",
            "user_id": 1001,
            "message_type": "group",
            "message_id": 7,
            "message": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "at", "data": {"qq": "42"}},
                {
                    "type": "image",
                    "data": {"file": "image-id", "url": "https://example.test/image.png"},
                },
                {"type": "record", "data": {"file": "audio-id"}},
                {"type": "video", "data": {"file": "video-id"}},
                {"type": "reply", "data": {"id": "6"}},
                {"type": "face", "data": {"id": "123"}},
            ],
            "raw_message": "hello",
            "font": 0,
            "sender": {"user_id": 1001, "nickname": "nickname", "card": "group card"},
            "group_id": 2002,
        }
    )


def _onebot_v11_private_event() -> Any:
    onebot = importlib.import_module("nonebot.adapters.onebot.v11")
    return onebot.PrivateMessageEvent.model_validate(
        {
            "time": 1_720_000_000,
            "self_id": 42,
            "post_type": "message",
            "sub_type": "friend",
            "user_id": 1001,
            "message_type": "private",
            "message_id": 8,
            "message": [{"type": "text", "data": {"text": "private"}}],
            "raw_message": "private",
            "font": 0,
            "sender": {"user_id": 1001, "nickname": "nickname"},
        }
    )


def _onebot_v12_event(detail_type: str) -> Any:
    onebot = importlib.import_module("nonebot.adapters.onebot.v12")
    event_class = {
        "private": onebot.PrivateMessageEvent,
        "group": onebot.GroupMessageEvent,
        "channel": onebot.ChannelMessageEvent,
    }[detail_type]
    value: dict[str, Any] = {
        "id": f"event-{detail_type}",
        "time": datetime(2026, 8, 9, 1, 2, tzinfo=UTC),
        "type": "message",
        "detail_type": detail_type,
        "sub_type": "",
        "self": {"platform": "test", "user_id": "bot"},
        "message_id": f"message-{detail_type}",
        "message": [
            {"type": "text", "data": {"text": detail_type}},
            {"type": "mention", "data": {"user_id": "bot"}},
            {"type": "image", "data": {"file_id": "file-1"}},
            {"type": "reply", "data": {"message_id": "previous"}},
        ],
        "alt_message": detail_type,
        "user_id": "user",
    }
    if detail_type == "group":
        value["group_id"] = "group"
    elif detail_type == "channel":
        value["guild_id"] = "guild"
        value["channel_id"] = "channel"
    return event_class.model_validate(value)


def _satori_event(*, direct: bool) -> Any:
    satori_event = importlib.import_module("nonebot.adapters.satori.event")
    event_class = satori_event.PrivateMessageCreatedEvent if direct else satori_event.PublicMessageCreatedEvent
    value: dict[str, Any] = {
        "type": "message-created",
        "timestamp": 1_720_000_000_000,
        "login": {
            "sn": 1,
            "adapter": "test",
            "platform": "discord",
            "user": {"id": "bot"},
        },
        "channel": {"id": "direct" if direct else "channel", "type": 1 if direct else 0},
        "message": {
            "id": "message",
            "content": (
                '<quote id="previous">quoted</quote><at id="bot"/> '
                '<b>hello</b><img src="https://example.test/image.png"/>'
                '<custom foo="bar">nested</custom>'
                '<a href="https://example.test">link</a>'
                '<button type="action" id="go">Go</button><br/>'
            ),
        },
        "user": {"id": "user", "name": "account", "nick": "nickname", "is_bot": False},
        "sn": 9,
    }
    if not direct:
        value["guild"] = {"id": "guild"}
        value["member"] = {"nick": "member nickname"}
    return event_class.model_validate(value)


def _action(bot_id: str, action: SendMessage | CallApi) -> dict[str, Any]:
    return ActionEnvelope(
        runtime_id="nonebot",
        bot_id=bot_id,
        action=action,
    ).model_dump(mode="json")


def test_adapter_ids_and_strict_json_results() -> None:
    satori_models = importlib.import_module("nonebot.adapters.satori.models")
    source_timestamp = 1_720_000_000
    result = json_value(
        [
            satori_models.MessageObject(
                id="message",
                content="hello",
                created_at=datetime.fromtimestamp(source_timestamp),
            )
        ]
    )

    assert adapter_id("OneBot V11") == "onebot-v11"
    assert adapter_id("OneBot V12") == "onebot-v12"
    assert adapter_id("Satori") == "satori"
    assert result == [
        {
            "id": "message",
            "content": "hello",
            "channel": None,
            "guild": None,
            "member": None,
            "user": None,
            "created_at": datetime.fromtimestamp(source_timestamp, UTC).isoformat(),
            "updated_at": None,
            "referrer": None,
        }
    ]
    with pytest.raises(ValueError, match="NaN"):
        json_value(math.nan)
    with pytest.raises(TypeError, match="non-JSON"):
        json_value(object())


def test_onebot_v11_event_uses_group_fifo_key_and_original_segments() -> None:
    event = _onebot_v11_group_event()
    event.message.clear()
    envelope = normalize_event(FakeBot("42", "OneBot V11"), event)

    assert envelope.adapter == "onebot-v11"
    assert envelope.type == "message.group.normal"
    assert envelope.timestamp == datetime.fromtimestamp(1_720_000_000, UTC)
    assert envelope.conversation == ConversationRef(id="2002", type="group")
    assert envelope.actor is not None
    assert envelope.actor.id == "1001"
    assert envelope.actor.display_name == "group card"
    assert envelope.reply_token
    assert envelope.raw["group_id"] == 2002
    assert envelope.message is not None
    assert [segment.type for segment in envelope.message.segments] == [
        "text",
        "mention",
        "media",
        "media",
        "media",
        "reply",
        "adapter",
    ]
    assert envelope.message.segments[1].data["user_id"] == "42"
    assert envelope.message.segments[2].data["media_type"] == "image"
    assert envelope.message.segments[3].data["media_type"] == "voice"
    assert envelope.message.segments[3].data["adapter_type"] == "record"
    assert envelope.message.segments[5].data["message_id"] == "6"
    assert envelope.message.segments[6].data == {
        "adapter": "onebot-v11",
        "type": "face",
        "data": {"id": "123"},
    }


def test_onebot_v11_private_conversation_is_actor_not_composite_session() -> None:
    envelope = normalize_event(FakeBot("42", "OneBot V11"), _onebot_v11_private_event())

    assert envelope.conversation == ConversationRef(id="1001", type="private")
    assert envelope.type == "message.private.friend"


@pytest.mark.parametrize(
    ("detail_type", "expected"),
    [
        ("private", ConversationRef(id="user", type="private")),
        ("group", ConversationRef(id="group", type="group")),
        ("channel", ConversationRef(id="channel", type="channel", parent_id="guild")),
    ],
)
def test_onebot_v12_conversation_and_segments(
    detail_type: str,
    expected: ConversationRef,
) -> None:
    envelope = normalize_event(FakeBot("bot", "OneBot V12"), _onebot_v12_event(detail_type))

    assert envelope.adapter == "onebot-v12"
    assert envelope.type == f"message.{detail_type}"
    assert envelope.conversation == expected
    assert envelope.message is not None
    assert [segment.type for segment in envelope.message.segments] == [
        "text",
        "mention",
        "media",
        "reply",
    ]
    assert envelope.message.segments[1].data["user_id"] == "bot"
    assert envelope.message.segments[2].data["file_id"] == "file-1"


@pytest.mark.parametrize(
    ("direct", "expected"),
    [
        (True, ConversationRef(id="direct", type="private")),
        (False, ConversationRef(id="channel", type="channel", parent_id="guild")),
    ],
)
def test_satori_event_preserves_original_recursive_elements(
    direct: bool,
    expected: ConversationRef,
) -> None:
    event = _satori_event(direct=direct)
    event.get_message().clear()
    envelope = normalize_event(FakeBot("discord:bot", "Satori"), event)

    assert envelope.adapter == "satori"
    assert envelope.type == "message-created"
    assert envelope.timestamp.tzinfo is not None
    assert envelope.conversation == expected
    assert envelope.actor is not None
    assert envelope.actor.display_name == ("nickname" if direct else "member nickname")
    assert envelope.message is not None
    types = [segment.type for segment in envelope.message.segments]
    assert types == [
        "reply",
        "mention",
        "text",
        "media",
        "adapter",
        "adapter",
        "adapter",
        "adapter",
    ]
    assert envelope.message.segments[0].data["message_id"] == "previous"
    assert envelope.message.segments[2].data["styles"]
    assert envelope.message.segments[3].data["url"] == "https://example.test/image.png"
    custom = envelope.message.segments[4]
    assert custom.data["adapter"] == "satori"
    assert custom.data["type"] == "custom"
    assert custom.data["children"]

    restored = to_native_message("satori", envelope.message)
    assert '<quote id="previous">' in str(restored)
    assert '<custom foo="bar">nested</custom>' in str(restored)
    assert "<b>hello</b>" in str(restored)
    assert '<a href="https://example.test">link</a>' in str(restored)
    assert '<button type="action" id="go">Go</button>' in str(restored)
    assert "<br/>" in str(restored)


def test_native_message_conversion_rejects_cross_adapter_and_bad_media() -> None:
    with pytest.raises(AdapterContractError, match="targets"):
        to_native_message(
            "onebot-v11",
            Message(
                segments=(
                    Segment(
                        type="adapter",
                        data={"adapter": "satori", "type": "custom", "data": {}},
                    ),
                )
            ),
        )
    with pytest.raises(AdapterContractError, match="file_id"):
        to_native_message(
            "onebot-v12",
            Message(segments=(Segment(type="media", data={"media_type": "image", "url": "https://example.test"}),)),
        )
    with pytest.raises(AdapterContractError, match="data.file"):
        to_native_message(
            "onebot-v11",
            Message(segments=(Segment(type="adapter", data={"type": "image", "data": {}}),)),
        )
    with pytest.raises(AdapterContractError, match="file_id"):
        to_native_message(
            "onebot-v12",
            Message(segments=(Segment(type="adapter", data={"type": "image", "data": {}}),)),
        )


def test_onebot_native_message_deeply_thaws_segment_data_for_real_encoder() -> None:
    encoder = importlib.import_module("nonebot.utils").DataclassEncoder
    native = to_native_message(
        "onebot-v11",
        Message(
            segments=(
                Segment(
                    type="adapter",
                    data={
                        "type": "custom",
                        "data": {"nested": {"values": (1, 2)}},
                    },
                ),
            )
        ),
    )

    assert type(native[0].data["nested"]) is dict
    assert type(native[0].data["nested"]["values"]) is list
    assert json.loads(json.dumps(native, cls=encoder))[0]["data"]["nested"] == {"values": [1, 2]}


def test_portable_voice_maps_to_onebot_v11_record() -> None:
    native = to_native_message(
        "onebot-v11",
        Message(
            segments=(
                Segment(
                    type="media",
                    data={"media_type": "voice", "url": "https://example.test/voice.ogg"},
                ),
            )
        ),
    )

    assert native[0].type == "record"
    assert native[0].data["file"] == "https://example.test/voice.ogg"


def test_satori_actor_falls_back_to_login_identity_when_is_bot_is_unknown() -> None:
    event = _satori_event(direct=True)
    event.user.id = "bot"
    event.user.is_bot = None

    envelope = normalize_event(FakeBot("discord:bot", "Satori"), event)

    assert envelope.actor is not None
    assert envelope.actor.is_bot is True


@pytest.mark.asyncio
async def test_nonebot_host_executes_structured_reply_and_legacy_adapter_segment() -> None:
    bot = FakeBot("42", "OneBot V11")
    event = _onebot_v11_group_event()
    envelope = normalize_event(bot, event)
    assert envelope.reply_token is not None
    host = NoneBotHost(FakeNoneBot(bot), bridge=None)  # type: ignore[arg-type]
    host.events[envelope.reply_token] = (bot, event)
    action = SendMessage(
        reply_token=envelope.reply_token,
        message=Message(
            segments=(
                Segment(type="text", data={"text": "reply"}),
                Segment(type="mention", data={"user_id": "1001"}),
                Segment(type="media", data={"media_type": "image", "url": "https://example.test/a.png"}),
                Segment(type="reply", data={"message_id": "7"}),
                Segment(type="adapter", data={"type": "image", "data": {"url": "https://example.test/b.png"}}),
            )
        ),
    )

    assert await host.execute_action(_action("42", action)) == (
        True,
        {"message_id": "sent"},
        None,
    )
    assert len(bot.replies) == 1
    target_event, native_message = bot.replies[0]
    assert target_event is event
    assert [segment.type for segment in native_message] == ["text", "at", "image", "reply", "image"]
    assert native_message[2].data["file"] == "https://example.test/a.png"
    assert native_message[4].data["file"] == "https://example.test/b.png"


@pytest.mark.asyncio
async def test_nonebot_host_rejects_expired_and_cross_bot_reply_tokens() -> None:
    source = FakeBot("42", "OneBot V11")
    selected = FakeBot("84", "OneBot V11")
    event = _onebot_v11_group_event()
    host = NoneBotHost(FakeNoneBot(source, selected), bridge=None)  # type: ignore[arg-type]
    host.events["source-token"] = (source, event)
    message = Message(segments=(Segment(type="text", data={"text": "reply"}),))

    assert await host.execute_action(_action("42", SendMessage(reply_token="expired", message=message))) == (
        False,
        None,
        "reply token is unknown or expired",
    )
    assert await host.execute_action(_action("84", SendMessage(reply_token="source-token", message=message))) == (
        False,
        None,
        "reply token belongs to a different bot",
    )
    assert source.replies == []
    assert selected.replies == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_name", "conversation", "expected_api", "expected_target"),
    [
        ("OneBot V11", ConversationRef(id="1001", type="private"), "send_private_msg", ("user_id", 1001)),
        ("OneBot V11", ConversationRef(id="2002", type="group"), "send_group_msg", ("group_id", 2002)),
        (
            "OneBot V12",
            ConversationRef(id="channel", type="channel", parent_id="guild"),
            "send_message",
            ("channel_id", "channel"),
        ),
    ],
)
async def test_nonebot_host_executes_onebot_proactive_routes(
    adapter_name: str,
    conversation: ConversationRef,
    expected_api: str,
    expected_target: tuple[str, Any],
) -> None:
    bot = FakeBot("bot", adapter_name)
    host = NoneBotHost(FakeNoneBot(bot), bridge=None)  # type: ignore[arg-type]
    action = SendMessage(
        conversation=conversation,
        message=Message(segments=(Segment(type="text", data={"text": "proactive"}),)),
    )

    assert (await host.execute_action(_action("bot", action)))[0] is True
    api, params = bot.api_calls[0]
    assert api == expected_api
    assert params[expected_target[0]] == expected_target[1]
    assert params["message"].extract_plain_text() == "proactive"


@pytest.mark.asyncio
async def test_nonebot_host_executes_satori_channel_send_and_call_api() -> None:
    bot = FakeBot("discord:bot", "Satori")
    host = NoneBotHost(FakeNoneBot(bot), bridge=None)  # type: ignore[arg-type]
    message = Message(segments=(Segment(type="text", data={"text": "hello"}),))

    sent = await host.execute_action(
        _action(
            "discord:bot",
            SendMessage(
                conversation=ConversationRef(id="direct-channel", type="private"),
                message=message,
            ),
        )
    )
    called = await host.execute_action(
        _action(
            "discord:bot",
            CallApi(
                api="message_get",
                params={
                    "channel_id": "direct-channel",
                    "message_id": "1",
                    "nested": {"values": (1, 2)},
                },
            ),
        )
    )

    assert sent == (True, {"message_id": "sent"}, None)
    assert bot.channel_sends[0][0] == "direct-channel"
    assert str(bot.channel_sends[0][1]) == "hello"
    assert called == (True, {"message_id": "sent"}, None)
    assert bot.api_calls == [
        (
            "message_get",
            {
                "channel_id": "direct-channel",
                "message_id": "1",
                "nested": {"values": [1, 2]},
            },
        )
    ]
    assert type(bot.api_calls[0][1]["nested"]) is dict
    assert type(bot.api_calls[0][1]["nested"]["values"]) is list
