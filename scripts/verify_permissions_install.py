"""Verify the installed permission wheel without importing workspace sources."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import tempfile
from pathlib import Path
from typing import cast

import liteyukibot_permissions
from liteyukibot_permissions import OPERATOR, PERMISSION_SERVICE, PermissionService

import liteyukibot
from liteyukibot import PluginDefinition
from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope
from liteyukibot.testing import PluginTestHarness

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _verify_import_sources() -> None:
    imported = (
        Path(liteyukibot.__file__).resolve(),
        Path(liteyukibot_permissions.__file__).resolve(),
    )
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")


def _installed_plugin() -> PluginDefinition:
    matches = tuple(
        item
        for item in importlib.metadata.entry_points(group="liteyukibot.plugins")
        if item.name == "liteyukibot.permissions"
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected one permission entry point, found {len(matches)}")
    candidate = matches[0].load()
    if not isinstance(candidate, PluginDefinition):
        raise TypeError("permission entry point did not resolve to PluginDefinition")
    return candidate


async def verify(expected_version: str | None = None) -> None:
    _verify_import_sources()

    definition = _installed_plugin()
    config = {
        "operators": [
            {"runtime_id": "runtime", "bot_id": "bot", "actor_id": "operator"},
        ]
    }
    event = EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="message",
        conversation=ConversationRef(id="conversation"),
        actor=ActorRef(id="operator"),
    )
    with tempfile.TemporaryDirectory() as directory:
        async with PluginTestHarness(definition, root=Path(directory), config=config) as harness:
            service = cast(PermissionService, harness.require_service(PERMISSION_SERVICE))
            if not service.allows(event, OPERATOR):
                raise RuntimeError("installed permission service rejected its configured operator")

    observed = {
        "liteyukibot-v7": importlib.metadata.version("liteyukibot-v7"),
        "liteyukibot-v7-permissions": importlib.metadata.version(
            "liteyukibot-v7-permissions"
        ),
    }
    if expected_version is not None and observed["liteyukibot-v7-permissions"] != expected_version:
        raise RuntimeError(
            f"expected liteyukibot-v7-permissions {expected_version}; observed {observed}"
        )
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    asyncio.run(verify(arguments.expected_version))
