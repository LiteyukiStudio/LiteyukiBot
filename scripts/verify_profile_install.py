"""Verify the installed profile wheel without importing workspace sources."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import tempfile
from pathlib import Path
from typing import cast

import liteyukibot_profile
import liteyukibot_resources
from liteyukibot_commands import COMMAND_SERVICE, CommandService
from liteyukibot_commands.service import create_command_service
from liteyukibot_permissions import PERMISSION_SERVICE, PermissionService, Principal
from liteyukibot_profile import PROFILE_SERVICE, ProfileService, ProfileSnapshot
from liteyukibot_resources import RESOURCE_SERVICE, ResourceService
from liteyukibot_resources.service import create_resource_service

import liteyukibot
from liteyukibot import AuthorizationContext, PluginDefinition
from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope
from liteyukibot.i18n import I18N_SERVICE, Translator
from liteyukibot.logging import get_logger
from liteyukibot.resource_packs import ResourceCatalog
from liteyukibot.testing import PluginTestHarness

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _verify_import_sources() -> None:
    imported = (
        Path(liteyukibot.__file__).resolve(),
        Path(liteyukibot_profile.__file__).resolve(),
        Path(liteyukibot_resources.__file__).resolve(),
    )
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")


def _installed_plugin() -> PluginDefinition:
    matches = tuple(
        item
        for item in importlib.metadata.entry_points(group="liteyukibot.plugins")
        if item.name == "liteyukibot.profile"
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected one profile entry point, found {len(matches)}")
    candidate = matches[0].load()
    if not isinstance(candidate, PluginDefinition):
        raise TypeError("profile entry point did not resolve to PluginDefinition")
    return candidate


class _PermissionStub:
    def allows(self, _event: EventEnvelope, _capability: str) -> bool:
        return False


def _event() -> EventEnvelope:
    return EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="message",
        conversation=ConversationRef(id="conversation"),
        actor=ActorRef(id="user"),
    )


async def verify(expected_version: str | None = None) -> None:
    _verify_import_sources()
    definition = _installed_plugin()
    permissions = cast(PermissionService, _PermissionStub())
    commands = cast(CommandService, create_command_service({}, permissions, get_logger(component="verify")))
    translator = Translator.from_resources(
        ResourceCatalog.load(".", plugin_packs=definition.manifest.resource_packs),
        "en-US",
    )[0]
    resources = create_resource_service(permissions, commands, translator)
    with tempfile.TemporaryDirectory() as directory:
        async with PluginTestHarness(
            definition,
            root=Path(directory),
            dependencies={
                PERMISSION_SERVICE: permissions,
                COMMAND_SERVICE: commands,
                RESOURCE_SERVICE: resources,
                I18N_SERVICE: translator,
            },
        ) as harness:
            profile = cast(ProfileService, harness.require_service(PROFILE_SERVICE))
            user = Principal("runtime", "bot", "user")
            if await profile.get(user) != ProfileSnapshot(user):
                raise RuntimeError("installed profile service did not return defaults")
            resource_service = cast(ResourceService, harness.require_service(RESOURCE_SERVICE))
            await resource_service.set(_event(), ("profile",), "nickname", "Alice")
            if await profile.get(user) != ProfileSnapshot(user, nickname="Alice"):
                raise RuntimeError("installed profile service did not persist a resource update")
            handlers = harness.context._tool_handlers
            authorization = AuthorizationContext(
                event_id="tool-event",
                runtime_id="runtime",
                bot_id="bot",
                actor_id="user",
            )
            inspect_tool = handlers["liteyukibot.profile.inspect"]
            result = await inspect_tool(authorization, {})
            if result != {"nickname": "Alice", "language": "zh-CN"}:
                raise RuntimeError("installed profile inspect Tool returned an unexpected value")

    observed = {
        name: importlib.metadata.version(name)
        for name in (
            "liteyukibot-v7",
            "liteyukibot-v7-permissions",
            "liteyukibot-v7-commands",
            "liteyukibot-v7-resources",
            "liteyukibot-v7-profile",
        )
    }
    if expected_version is not None and observed["liteyukibot-v7-profile"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-profile {expected_version}; observed {observed}")
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    asyncio.run(verify(arguments.expected_version))
