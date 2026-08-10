"""Verify the installed resource wheel without importing workspace sources."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import tempfile
from pathlib import Path
from typing import cast

import liteyukibot_resources
from liteyukibot_permissions import PERMISSION_SERVICE, PermissionService
from liteyukibot_resources import RESOURCE_SERVICE, ResourceField, ResourceProvider, ResourceSpec
from liteyukibot_resources.service import ResourceService

import liteyukibot
from liteyukibot import PluginDefinition
from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope
from liteyukibot.testing import PluginTestHarness

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _verify_import_sources() -> None:
    imported = (
        Path(liteyukibot.__file__).resolve(),
        Path(liteyukibot_resources.__file__).resolve(),
    )
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")


def _installed_plugin() -> PluginDefinition:
    matches = tuple(
        item
        for item in importlib.metadata.entry_points(group="liteyukibot.plugins")
        if item.name == "liteyukibot.resources"
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected one resources entry point, found {len(matches)}")
    candidate = matches[0].load()
    if not isinstance(candidate, PluginDefinition):
        raise TypeError("resources entry point did not resolve to PluginDefinition")
    return candidate


class _Provider(ResourceProvider):
    async def inspect(self, _principal: object, _field: ResourceField) -> object:
        return "ok"

    async def set(self, _principal: object, _field: ResourceField, _value: object) -> None:
        return None

    async def delete(self, _principal: object, _field: ResourceField) -> None:
        return None


async def verify(expected_version: str | None = None) -> None:
    _verify_import_sources()
    definition = _installed_plugin()
    event = EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="message",
        conversation=ConversationRef(id="conversation"),
        actor=ActorRef(id="user"),
    )
    with tempfile.TemporaryDirectory() as directory:
        async with PluginTestHarness(
            definition,
            root=Path(directory),
            dependencies={PERMISSION_SERVICE: cast(PermissionService, _PermissionStub())},
        ) as harness:
            service = cast(ResourceService, harness.require_service(RESOURCE_SERVICE))
            service.register(
                ResourceSpec("verify", fields=(ResourceField("value", str),)),
                _Provider(),
                owner="verify",
            )
            if await service.inspect(event, ("verify",)) != {"value": "ok"}:
                raise RuntimeError("installed resources service returned an unexpected value")

    observed = {
        "liteyukibot-v7": importlib.metadata.version("liteyukibot-v7"),
        "liteyukibot-v7-resources": importlib.metadata.version("liteyukibot-v7-resources"),
    }
    if expected_version is not None and observed["liteyukibot-v7-resources"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-resources {expected_version}; observed {observed}")
    print(json.dumps(observed, sort_keys=True))


class _PermissionStub:
    def allows(self, _event: EventEnvelope, _capability: str) -> bool:
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    asyncio.run(verify(arguments.expected_version))
