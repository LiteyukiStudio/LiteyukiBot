"""Verify the installed command wheel without importing workspace sources."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import tempfile
from pathlib import Path
from typing import cast

import liteyukibot_commands
import liteyukibot_permissions
from liteyukibot_commands import COMMAND_SERVICE, CommandInvocation, CommandService, CommandSpec
from liteyukibot_permissions import PERMISSION_SERVICE, PUBLIC, Principal

import liteyukibot
from liteyukibot import PluginDefinition
from liteyukibot.events import (
    ActorRef,
    ConversationRef,
    EventEnvelope,
    HandlerResult,
    Message,
    Segment,
    SendMessage,
)
from liteyukibot.testing import PluginTestHarness

SOURCE_ROOT = Path(__file__).resolve().parents[1]


class PublicPermissions:
    def principal(self, event: EventEnvelope) -> Principal | None:
        if event.actor is None:
            return None
        return Principal(event.runtime_id, event.bot_id, event.actor.id)

    def allows(self, _event: EventEnvelope, permission: str) -> bool:
        return permission == PUBLIC


def _verify_import_sources() -> None:
    imported = (
        Path(liteyukibot.__file__).resolve(),
        Path(liteyukibot_commands.__file__).resolve(),
        Path(liteyukibot_permissions.__file__).resolve(),
    )
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")


def _installed_plugin() -> PluginDefinition:
    matches = tuple(
        item
        for item in importlib.metadata.entry_points(group="liteyukibot.plugins")
        if item.name == "liteyukibot.commands"
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected one command entry point, found {len(matches)}")
    candidate = matches[0].load()
    if not isinstance(candidate, PluginDefinition):
        raise TypeError("command entry point did not resolve to PluginDefinition")
    return candidate


async def verify() -> None:
    _verify_import_sources()
    definition = _installed_plugin()
    event = EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="message",
        conversation=ConversationRef(id="conversation"),
        actor=ActorRef(id="user"),
        message=Message(segments=(Segment(type="text", data={"text": "/echo wheel"}),)),
        reply_token="reply-token",
    )
    with tempfile.TemporaryDirectory() as directory:
        async with PluginTestHarness(
            definition,
            root=Path(directory),
            dependencies={PERMISSION_SERVICE: PublicPermissions()},
        ) as harness:
            service = cast(CommandService, harness.require_service(COMMAND_SERVICE))

            def echo(invocation: CommandInvocation) -> HandlerResult:
                return invocation.reply(invocation.raw_arguments)

            service.register(CommandSpec("echo"), echo, owner="wheel-verifier")
            result = await harness.publish(event)
            if not result.stopped or len(harness.recorded_actions) != 1:
                raise RuntimeError("installed command router did not stop and reply")
            action = harness.recorded_actions[0].action
            if not isinstance(action, SendMessage) or action.message.plain_text != "wheel":
                raise RuntimeError("installed command router produced an invalid reply")

    observed = {
        name: importlib.metadata.version(name)
        for name in (
            "liteyukibot-v7",
            "liteyukibot-v7-permissions",
            "liteyukibot-v7-commands",
        )
    }
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(verify())
