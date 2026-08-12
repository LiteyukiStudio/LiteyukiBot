"""Verify the installed first-party plugin topology outside workspace sources."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import tempfile
from pathlib import Path
from typing import cast

import liteyukibot_commands
import liteyukibot_essentials
import liteyukibot_permissions
from liteyukibot_commands import COMMAND_SERVICE, CommandService

import liteyukibot
from liteyukibot import LiteyukiApp, PluginDefinition
from liteyukibot.config import AppSettings, CoreSettings, PluginSettings
from liteyukibot.events import (
    ActionEnvelope,
    ActionResult,
    ActorRef,
    ConversationRef,
    EventEnvelope,
    Message,
    Segment,
    SendMessage,
)
from liteyukibot.logging import get_logger

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _verify_import_sources() -> None:
    imported = (
        Path(liteyukibot.__file__).resolve(),
        Path(liteyukibot_commands.__file__).resolve(),
        Path(liteyukibot_essentials.__file__).resolve(),
        Path(liteyukibot_permissions.__file__).resolve(),
    )
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")


def _verify_entry_points() -> None:
    expected = {
        "liteyukibot.permissions",
        "liteyukibot.commands",
        "liteyukibot.essentials",
    }
    matches = tuple(
        item
        for item in importlib.metadata.entry_points(group="liteyukibot.plugins")
        if item.name in expected
    )
    if {item.name for item in matches} != expected:
        raise RuntimeError(f"first-party entry point mismatch: {matches}")
    if any(not isinstance(item.load(), PluginDefinition) for item in matches):
        raise TypeError("a first-party entry point did not resolve to PluginDefinition")


def _event(text: str, actor_id: str) -> EventEnvelope:
    return EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="message",
        conversation=ConversationRef(id="conversation", type="group"),
        actor=ActorRef(id=actor_id),
        message=Message(segments=(Segment(type="text", data={"text": text}),)),
        reply_token="reply-token",
    )


async def verify(expected_version: str | None = None) -> None:
    _verify_import_sources()
    _verify_entry_points()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        settings = AppSettings(
            core=CoreSettings(data_dir=root / "data", cache_dir=root / "cache"),
            plugins=PluginSettings(
                enabled=(
                    "liteyukibot.permissions",
                    "liteyukibot.commands",
                    "liteyukibot.essentials",
                ),
                config={
                    "liteyukibot.permissions": {
                        "roles": {"operator": ["liteyukibot.status.read"]},
                        "grants": [
                            {
                                "runtime_id": "runtime",
                                "bot_id": "bot",
                                "actor_id": "operator",
                                "roles": ["operator"],
                            }
                        ]
                    },
                    "liteyukibot.essentials": {"language": "en"},
                },
            ),
        )
        actions: list[ActionEnvelope] = []

        async def record(_event: EventEnvelope, action: ActionEnvelope) -> ActionResult:
            actions.append(action)
            return ActionResult(action_id=action.action_id, success=True)

        app = LiteyukiApp(settings, logger=get_logger(component="essentials-wheel"))
        app.events._action_executor = record
        await app.start()
        try:
            commands = cast(CommandService, app.services.require(COMMAND_SERVICE))
            if [item.spec.name for item in commands.snapshot()] != ["help", "status"]:
                raise RuntimeError("essential commands were not registered")

            user_help = _event("/help", "user")
            result = await app.events.publish(user_help)
            if not result.stopped or len(actions) != 1:
                raise RuntimeError("installed help command did not stop and reply")
            help_action = actions[-1]
            message = help_action.action
            if not isinstance(message, SendMessage):
                raise TypeError("installed help command did not produce SendMessage")
            if "/status" in message.message.plain_text or "Available commands:" not in message.message.plain_text:
                raise RuntimeError("installed help command did not filter protected commands")
            if help_action.event_id != user_help.id or message.reply_token != user_help.reply_token:
                raise RuntimeError("installed help reply lost event correlation")

            result = await app.events.publish(_event("/status", "operator"))
            if not result.stopped or len(actions) != 2:
                raise RuntimeError("installed capability-protected status command did not reply")
            status_message = actions[-1].action
            if not isinstance(status_message, SendMessage) or not status_message.message.plain_text.startswith(
                f"LiteyukiBot {liteyukibot.__version__}\nState: ready"
            ):
                raise RuntimeError("installed status command produced invalid text")
        finally:
            await app.stop()

    observed = {
        name: importlib.metadata.version(name)
        for name in (
            "liteyukibot-v7",
            "liteyukibot-v7-permissions",
            "liteyukibot-v7-commands",
            "liteyukibot-v7-essentials",
        )
    }
    if expected_version is not None and observed["liteyukibot-v7-essentials"] != expected_version:
        raise RuntimeError(
            f"expected liteyukibot-v7-essentials {expected_version}; observed {observed}"
        )
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    asyncio.run(verify(arguments.expected_version))
