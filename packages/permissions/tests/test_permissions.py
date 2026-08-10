from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from liteyukibot_permissions import (
    OPERATOR,
    PERMISSION_SERVICE,
    PUBLIC,
    PermissionService,
    Principal,
    plugin,
)

from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope
from liteyukibot.exceptions import PluginError, ServiceError
from liteyukibot.testing import PluginTestHarness


def event(*, runtime_id: str = "nonebot", bot_id: str = "bot-1", actor_id: str | None = "user-1") -> EventEnvelope:
    return EventEnvelope(
        runtime_id=runtime_id,
        adapter="onebot.v11",
        bot_id=bot_id,
        type="message",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=None if actor_id is None else ActorRef(id=actor_id),
    )


@pytest.mark.asyncio
async def test_permission_service_matches_exact_operator_identity(tmp_path: Path) -> None:
    config = {
        "operators": [
            {"runtime_id": "nonebot", "bot_id": "bot-1", "actor_id": "user-1"},
        ]
    }
    async with PluginTestHarness(plugin, root=tmp_path, config=config) as harness:
        service = cast(PermissionService, harness.require_service(PERMISSION_SERVICE))

        assert service.principal(event()) == Principal("nonebot", "bot-1", "user-1")
        assert service.allows(event(actor_id=None), PUBLIC) is True
        assert service.allows(event(), OPERATOR) is True
        assert service.allows(event(runtime_id="other"), OPERATOR) is False
        assert service.allows(event(bot_id="bot-2"), OPERATOR) is False
        assert service.allows(event(actor_id="user-2"), OPERATOR) is False
        assert service.allows(event(actor_id=None), OPERATOR) is False
        assert service.allows(event(), "plugin.manage") is False

    with pytest.raises(ServiceError, match="unavailable"):
        harness.require_service(PERMISSION_SERVICE)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"unknown": True}, "unknown permission config keys"),
        ({"operators": "user-1"}, "must be a sequence"),
        ({"operators": ["user-1"]}, "must be an object"),
        (
            {"operators": [{"runtime_id": "nonebot", "bot_id": "bot-1"}]},
            "missing actor_id",
        ),
        (
            {
                "operators": [
                    {"runtime_id": "nonebot", "bot_id": "bot-1", "actor_id": "user-1"},
                    {"runtime_id": "nonebot", "bot_id": "bot-1", "actor_id": "user-1"},
                ]
            },
            "duplicates an earlier identity",
        ),
        (
            {
                "operators": [
                    {"runtime_id": " nonebot", "bot_id": "bot-1", "actor_id": "user-1"},
                ]
            },
            "non-empty trimmed string",
        ),
        (
            {
                "operators": [
                    {"runtime_id": "nonebot", "bot_id": 1, "actor_id": "user-1"},
                ]
            },
            "fields must be strings",
        ),
    ],
)
async def test_permission_plugin_rejects_invalid_configuration(
    tmp_path: Path,
    config: dict[str, object],
    message: str,
) -> None:
    harness = PluginTestHarness(plugin, root=tmp_path, config=config)

    with pytest.raises(PluginError, match="setup failed") as raised:
        await harness.start()

    assert raised.value.__cause__ is not None
    assert message in str(raised.value.__cause__)


def test_permission_plugin_manifest_publishes_versioned_service() -> None:
    assert plugin.manifest.id == "liteyukibot.permissions"
    assert plugin.manifest.version == "0.1.0a1"
    assert plugin.manifest.provides == (PERMISSION_SERVICE,)
