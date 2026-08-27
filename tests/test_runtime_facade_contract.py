from __future__ import annotations

from typing import Any, cast

import pytest
from liteyukibot_broker import (
    PORTABLE_RUNTIME_API_VERSION,
    portable_runtime_api_catalog,
    runtime_api_catalog_fingerprint,
)
from liteyukibot_runtime_nonebot.host import _runtime_api_declarations as nonebot_declarations
from liteyukibot_runtime_nonebot_api import NoneBotBotSnapshot, NoneBotEventSnapshot
from pydantic import ValidationError

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
    with pytest.raises(ValidationError, match="contains non-JSON value"):
        SendResult(sent=True, result=cast(Any, {"bad": object()}))


def test_nonebot_provider_catalog_uses_the_canonical_portable_contract() -> None:
    nonebot = {item.api_id: item for item in nonebot_declarations()}

    assert set(nonebot) == {"event.snapshot", "event.send", "bot.snapshot", "bot.send"}
    assert tuple(nonebot.values()) == portable_runtime_api_catalog("nonebot")
    nonebot_fingerprint = runtime_api_catalog_fingerprint(tuple(nonebot.values()))
    assert nonebot_fingerprint == runtime_api_catalog_fingerprint(tuple(reversed(tuple(nonebot.values()))))
    for api_id in nonebot:
        assert nonebot[api_id].version == PORTABLE_RUNTIME_API_VERSION


def test_nonebot_snapshot_names_are_aliases_of_kernel_models() -> None:
    assert NoneBotEventSnapshot is EventSnapshot
    assert NoneBotBotSnapshot is BotSnapshot
