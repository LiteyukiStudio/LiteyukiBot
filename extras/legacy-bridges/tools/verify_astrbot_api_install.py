"""Verify the independent AstrBot runtime API facade in an Alpha bundle."""

from __future__ import annotations

import argparse
import importlib.metadata

from liteyukibot_runtime_astrbot_api import (
    AstrBotBotProxy,
    AstrBotBotSnapshot,
    AstrBotEventProxy,
    AstrBotEventSnapshot,
    bot_proxy_factory,
    proxy_factory,
)

from liteyukibot.runtime_api import BotSnapshot, EventSnapshot, RuntimeBinding, SendResult


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    observed = importlib.metadata.version("liteyukibot-v7-runtime-astrbot-api")
    if observed != args.expected_version:
        raise RuntimeError(f"AstrBot API version {observed!r} does not match {args.expected_version!r}")
    entry_points = {
        entry.name: entry.value
        for entry in importlib.metadata.entry_points(group="liteyukibot.runtime_api_proxies")
        if entry.name in {"astrbot.event", "astrbot.bot"}
    }
    expected = {
        "astrbot.event": "liteyukibot_runtime_astrbot_api:proxy_factory",
        "astrbot.bot": "liteyukibot_runtime_astrbot_api:bot_proxy_factory",
    }
    if entry_points != expected:
        raise RuntimeError(f"unexpected AstrBot API facade entry points: {entry_points!r}")
    event = AstrBotEventSnapshot.model_validate(
        {
            "source_event_id": "source-event",
            "runtime_id": "astrbot",
            "adapter": "aiocqhttp",
            "bot_id": "bot-1",
            "event_type": "message.created",
            "conversation": {"id": "chat-1", "type": "group"},
            "extensions": {"astrbot": {"platform_id": "qq", "session_id": "session-1"}},
        }
    )
    bot = AstrBotBotSnapshot.model_validate(
        {
            "bot_id": "bot-1",
            "adapter": "aiocqhttp",
            "extensions": {"astrbot": {"platform_id": "qq", "platform_name": "aiocqhttp"}},
        }
    )
    if not isinstance(event, EventSnapshot) or not isinstance(bot, BotSnapshot):
        raise RuntimeError("AstrBot snapshots do not use kernel-owned DTOs")
    if event.platform_id != "qq" or bot.platform_name != "aiocqhttp":
        raise RuntimeError("AstrBot compatibility properties did not read extensions")
    if not SendResult(sent=True).sent:
        raise RuntimeError("AstrBot SendResult is not usable")
    event_proxy = proxy_factory(
        binding=RuntimeBinding("astrbot", "event", "^1.2", True, "astrbot_event"),
        backend=None,
        context=None,
    )
    bot_proxy = bot_proxy_factory(
        binding=RuntimeBinding("astrbot", "bot", "^1.2", True, "astrbot_bot"),
        backend=None,
        context=None,
    )
    if not isinstance(event_proxy, AstrBotEventProxy) or not isinstance(bot_proxy, AstrBotBotProxy):
        raise RuntimeError("AstrBot proxy entry points returned the wrong facade type")
    if event_proxy.available or bot_proxy.available:
        raise RuntimeError("unavailable AstrBot runtime proxies reported availability")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
