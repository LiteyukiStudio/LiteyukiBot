from __future__ import annotations

from typing import Any, cast

import pytest
from liteyukibot_runtime_astrbot.host import _runtime_api_declarations as astrbot_declarations
from liteyukibot_runtime_astrbot_api import AstrBotBotSnapshot, AstrBotEventSnapshot
from liteyukibot_runtime_nonebot.host import _runtime_api_declarations as nonebot_declarations
from liteyukibot_runtime_nonebot_api import NoneBotBotSnapshot, NoneBotEventSnapshot
from pydantic import ValidationError

from liteyukibot.broker import PORTABLE_RUNTIME_API_VERSION
from liteyukibot.events import ActorRef, ConversationRef, JsonValue, Message, Segment
from liteyukibot.runtime_api import BotSnapshot, EventSnapshot, SendResult


def _event_snapshot() -> EventSnapshot:
    return EventSnapshot(
        source_event_id="v1:bridge:adapter%3Abot:event",
        runtime_id="bridge",
        adapter="adapter",
        bot_id="bot",
        event_type="message.created",
        conversation=ConversationRef(id="chat", type="group"),
        actor=ActorRef(id="user", display_name="User"),
        message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
    )


def test_runtime_facade_models_are_json_safe_and_round_trip() -> None:
    event = _event_snapshot()
    bot = BotSnapshot(bot_id="bot", adapter="adapter", capabilities=("message.send",))
    result = SendResult(sent=True, result={"message_id": "sent"})

    assert EventSnapshot.model_validate_json(event.model_dump_json()) == event
    assert BotSnapshot.model_validate_json(bot.model_dump_json()) == bot
    assert SendResult.model_validate_json(result.model_dump_json()) == result
    dumped = cast(dict[str, JsonValue], event.model_dump(mode="json"))
    assert dumped["extensions"] == {}


def test_runtime_facade_rejects_non_json_send_results() -> None:
    with pytest.raises(ValidationError, match="Input should be a valid"):
        SendResult(sent=True, result=cast(Any, {"bad": object()}))


def test_provider_catalogs_share_the_canonical_portable_contract() -> None:
    nonebot = {item.api_id: item for item in nonebot_declarations()}
    astrbot = {item.api_id: item for item in astrbot_declarations()}

    assert set(nonebot) == {"event.snapshot", "event.send", "bot.snapshot", "bot.send"}
    assert set(astrbot) == set(nonebot)
    for api_id in nonebot:
        assert nonebot[api_id].version == PORTABLE_RUNTIME_API_VERSION
        assert astrbot[api_id].version == PORTABLE_RUNTIME_API_VERSION
        assert astrbot[api_id].input_schema == nonebot[api_id].input_schema
        assert astrbot[api_id].output_schema == nonebot[api_id].output_schema


def test_provider_snapshot_names_are_compatibility_views_of_kernel_models() -> None:
    event = _event_snapshot().model_dump(mode="json")
    event["extensions"] = {
        "astrbot": {
            "platform_id": "qq",
            "platform_name": "aiocqhttp",
            "session_id": "session-1",
            "message_type": "group",
        }
    }
    astrbot_event = AstrBotEventSnapshot.model_validate(event)
    astrbot_bot = AstrBotBotSnapshot.model_validate(
        {
            "bot_id": "bot",
            "adapter": "aiocqhttp",
            "extensions": {"astrbot": {"platform_id": "qq", "platform_name": "aiocqhttp"}},
        }
    )

    assert isinstance(astrbot_event, EventSnapshot)
    assert astrbot_event.message is not None
    assert astrbot_event.message_text == "hello"
    assert astrbot_event.platform_id == "qq"
    assert astrbot_event.session_id == "session-1"
    assert astrbot_event.message_segments[0].type == "text"
    assert astrbot_bot.platform_id == "qq"
    assert astrbot_bot.platform_name == "aiocqhttp"
    assert NoneBotEventSnapshot is EventSnapshot
    assert NoneBotBotSnapshot is BotSnapshot
