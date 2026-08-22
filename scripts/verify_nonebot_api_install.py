"""Verify the independent NoneBot runtime API facade in an Alpha bundle."""

from __future__ import annotations

import argparse
import importlib.metadata

from liteyukibot_runtime_nonebot_api import (
    NoneBotBotProxy,
    NoneBotBotSnapshot,
    NoneBotEventProxy,
    NoneBotEventSnapshot,
    bot_proxy_factory,
    event_proxy_factory,
)

from liteyukibot.events import ConversationRef
from liteyukibot.runtime_api import BotSnapshot, EventSnapshot, RuntimeBinding, SendResult


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    distribution = "liteyukibot-v7-runtime-nonebot-api"
    observed = importlib.metadata.version(distribution)
    if observed != args.expected_version:
        raise RuntimeError(f"NoneBot API version {observed!r} does not match {args.expected_version!r}")
    entry_points = {
        entry.name: entry.value
        for entry in importlib.metadata.entry_points(group="liteyukibot.runtime_api_proxies")
        if entry.name in {"nonebot.event", "nonebot.bot"}
    }
    expected = {
        "nonebot.event": "liteyukibot_runtime_nonebot_api:event_proxy_factory",
        "nonebot.bot": "liteyukibot_runtime_nonebot_api:bot_proxy_factory",
    }
    if entry_points != expected:
        raise RuntimeError(f"unexpected NoneBot API facade entry points: {entry_points!r}")
    event = NoneBotEventSnapshot.model_validate(
        {
            "source_event_id": "source-event",
            "runtime_id": "nonebot",
            "adapter": "onebot-v11",
            "bot_id": "bot-1",
            "event_type": "message.created",
            "conversation": {"id": "chat-1", "type": "group"},
        }
    )
    bot = NoneBotBotSnapshot.model_validate({"bot_id": "bot-1", "adapter": "onebot-v11"})
    if not isinstance(event, EventSnapshot) or not isinstance(bot, BotSnapshot):
        raise RuntimeError("NoneBot snapshots do not use kernel-owned DTOs")
    if not SendResult(sent=True).sent:
        raise RuntimeError("NoneBot SendResult is not usable")
    event_proxy = event_proxy_factory(
        binding=RuntimeBinding("nonebot", "event", "^1.2", True, "nonebot_event"),
        backend=None,
        context=None,
    )
    bot_proxy = bot_proxy_factory(
        binding=RuntimeBinding("nonebot", "bot", "^1.2", True, "nonebot_bot"),
        backend=None,
        context=None,
    )
    if not isinstance(event_proxy, NoneBotEventProxy) or not isinstance(bot_proxy, NoneBotBotProxy):
        raise RuntimeError("NoneBot proxy entry points returned the wrong facade type")
    if event_proxy.available or bot_proxy.available:
        raise RuntimeError("unavailable NoneBot runtime proxies reported availability")
    if event.conversation != ConversationRef(id="chat-1", type="group"):
        raise RuntimeError("NoneBot snapshot conversation DTO did not round-trip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
