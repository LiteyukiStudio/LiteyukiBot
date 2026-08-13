from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from liteyukibot_permissions import (
    PERMISSION_SERVICE,
    PUBLIC,
    ManagementPermissionService,
    PermissionAuditService,
    PermissionDecision,
    PermissionService,
    PermissionSnapshot,
    Principal,
    plugin,
)
from liteyukibot_permissions.service import create_permission_service

from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope
from liteyukibot.exceptions import PluginError, ServiceError
from liteyukibot.management import MANAGEMENT_ADMIN, ManagementCaller
from liteyukibot.testing import PluginTestHarness

STATUS_READ = "liteyukibot.status.read"
PLUGIN_MANAGE = "example.plugin.manage"


def event(*, runtime_id: str = "nonebot", bot_id: str = "bot-1", actor_id: str | None = "user-1") -> EventEnvelope:
    return EventEnvelope(
        runtime_id=runtime_id,
        adapter="onebot.v11",
        bot_id=bot_id,
        type="message",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=None if actor_id is None else ActorRef(id=actor_id),
    )


def permission_config() -> dict[str, object]:
    return {
        "roles": {
            "operator": [STATUS_READ, PLUGIN_MANAGE],
            "auditor": [STATUS_READ],
        },
        "grants": [
            {
                "runtime_id": "nonebot",
                "bot_id": "bot-1",
                "actor_id": "user-1",
                "roles": ["operator"],
                "capabilities": ["example.echo.use"],
            }
        ],
        "management_grants": [{"id": "plugin.example", "capabilities": [MANAGEMENT_ADMIN]}],
    }


@pytest.mark.asyncio
async def test_permission_service_resolves_roles_and_exact_capabilities(tmp_path: Path) -> None:
    async with PluginTestHarness(plugin, root=tmp_path, config=permission_config()) as harness:
        service = cast(PermissionService, harness.require_service(PERMISSION_SERVICE))

        snapshot = service.resolve(event())
        assert snapshot == PermissionSnapshot(
            Principal("nonebot", "bot-1", "user-1"),
            frozenset({"operator"}),
            frozenset({PUBLIC, STATUS_READ, PLUGIN_MANAGE, "example.echo.use"}),
        )
        assert service.principal(event()) == snapshot.principal
        assert service.allows(event(), PUBLIC) is True
        assert service.allows(event(), STATUS_READ) is True
        assert service.allows(event(), "example.echo.use") is True
        assert service.allows(event(), "missing.capability") is False

    with pytest.raises(ServiceError, match="unavailable"):
        harness.require_service(PERMISSION_SERVICE)


@pytest.mark.asyncio
async def test_permission_service_isolates_principals_and_anonymous_events(tmp_path: Path) -> None:
    async with PluginTestHarness(plugin, root=tmp_path, config=permission_config()) as harness:
        service = cast(PermissionService, harness.require_service(PERMISSION_SERVICE))
        management_service = cast(ManagementPermissionService, service)

        for denied in (
            event(runtime_id="other"),
            event(bot_id="bot-2"),
            event(actor_id="user-2"),
        ):
            snapshot = service.resolve(denied)
            assert snapshot.principal is not None
            assert snapshot.roles == frozenset()
            assert snapshot.capabilities == frozenset({PUBLIC})
            assert service.allows(denied, STATUS_READ) is False

        anonymous = service.resolve(event(actor_id=None))
        assert anonymous.principal is None
        assert anonymous.roles == frozenset()
        assert anonymous.capabilities == frozenset({PUBLIC})
        assert service.allows(event(actor_id=None), PUBLIC) is True
        assert service.allows(event(actor_id=None), STATUS_READ) is False
        assert management_service.allows_management(
            ManagementCaller("plugin.example", "plugin", frozenset()), MANAGEMENT_ADMIN
        )
        assert not management_service.allows_management(
            ManagementCaller("plugin.other", "plugin", frozenset()), MANAGEMENT_ADMIN
        )


@pytest.mark.asyncio
async def test_permission_service_records_redacted_bounded_decisions(tmp_path: Path) -> None:
    async with PluginTestHarness(plugin, root=tmp_path, config=permission_config()) as harness:
        service = cast(PermissionAuditService, harness.require_service(PERMISSION_SERVICE))
        allowed_event = event()
        denied_event = event(actor_id="other")

        assert service.decide(allowed_event, STATUS_READ, component="commands.status") is True
        assert service.decide(denied_event, STATUS_READ, component="commands.status") is False
        decisions = service.audit()

    assert decisions == (
        PermissionDecision(
            capability=STATUS_READ,
            principal=Principal("nonebot", "bot-1", "user-1"),
            component="commands.status",
            event_id=allowed_event.id,
            allowed=True,
            reason="granted",
        ),
        PermissionDecision(
            capability=STATUS_READ,
            principal=Principal("nonebot", "bot-1", "other"),
            component="commands.status",
            event_id=denied_event.id,
            allowed=False,
            reason="not_granted",
        ),
    )
    assert service.audit(limit=1) == decisions[-1:]
    assert service.audit(limit=0) == ()
    with pytest.raises(ValueError, match="non-negative"):
        service.audit(limit=-1)


@pytest.mark.asyncio
async def test_permission_snapshot_is_deeply_immutable(tmp_path: Path) -> None:
    async with PluginTestHarness(plugin, root=tmp_path, config=permission_config()) as harness:
        service = cast(PermissionService, harness.require_service(PERMISSION_SERVICE))
        snapshot = service.resolve(event())

        with pytest.raises(AttributeError):
            snapshot.roles.add("other")  # type: ignore[attr-defined]
        with pytest.raises(AttributeError):
            snapshot.capabilities.add("other")  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"operators": []}, "unknown permission config keys"),
        ({"roles": []}, "roles must be an object"),
        ({"roles": {"operator": []}}, "must contain at least one capability"),
        ({"roles": {"operator": [PUBLIC]}}, "must not grant reserved capability public"),
        ({"roles": {"operator": [STATUS_READ, STATUS_READ]}}, "duplicates capability"),
        ({"roles": {"bad role": [STATUS_READ]}}, "without whitespace"),
        ({"grants": "user-1"}, "grants must be a sequence"),
        ({"grants": ["user-1"]}, "grants[0] must be an object"),
        (
            {"grants": [{"runtime_id": "nonebot", "bot_id": "bot-1", "roles": ["operator"]}]},
            "missing actor_id",
        ),
        (
            {
                "roles": {"operator": [STATUS_READ]},
                "grants": [
                    {
                        "runtime_id": "nonebot",
                        "bot_id": "bot-1",
                        "actor_id": "user-1",
                        "roles": ["operator"],
                        "unknown": True,
                    }
                ],
            },
            "unknown unknown",
        ),
        (
            {
                "roles": {"operator": [STATUS_READ]},
                "grants": [
                    {
                        "runtime_id": "nonebot",
                        "bot_id": "bot-1",
                        "actor_id": "user-1",
                        "roles": ["operator"],
                    },
                    {
                        "runtime_id": "nonebot",
                        "bot_id": "bot-1",
                        "actor_id": "user-1",
                        "capabilities": [PLUGIN_MANAGE],
                    },
                ],
            },
            "duplicates an earlier principal",
        ),
        (
            {"grants": [{"runtime_id": "nonebot", "bot_id": "bot-1", "actor_id": "user-1"}]},
            "must assign at least one role or capability",
        ),
        (
            {
                "grants": [
                    {
                        "runtime_id": "nonebot",
                        "bot_id": "bot-1",
                        "actor_id": "user-1",
                        "roles": ["missing"],
                    }
                ]
            },
            "references unknown roles: missing",
        ),
        (
            {
                "grants": [
                    {
                        "runtime_id": "nonebot",
                        "bot_id": "bot-1",
                        "actor_id": "user-1",
                        "capabilities": [PUBLIC],
                    }
                ]
            },
            "must not grant reserved capability public",
        ),
        (
            {
                "grants": [
                    {
                        "runtime_id": " nonebot",
                        "bot_id": "bot-1",
                        "actor_id": "user-1",
                        "capabilities": [STATUS_READ],
                    }
                ]
            },
            "non-empty trimmed string",
        ),
        (
            {
                "grants": [
                    {
                        "runtime_id": "nonebot",
                        "bot_id": "bot-1",
                        "actor_id": "user-1",
                        "capabilities": ["bad capability"],
                    }
                ]
            },
            "without whitespace",
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


def test_permission_snapshot_requires_public_capability() -> None:
    with pytest.raises(ValueError, match="must include public"):
        PermissionSnapshot(None, frozenset(), frozenset())


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (
            {
                "management_grants": [
                    {"id": "runtime-a", "capabilities": [STATUS_READ]},
                    {"id": "runtime-a", "capabilities": [PLUGIN_MANAGE]},
                ]
            },
            "duplicates an earlier management caller",
        ),
        (
            {"management_grants": [{"id": "runtime-a", "capabilities": [PUBLIC]}]},
            "must not grant reserved capability public",
        ),
    ],
)
def test_management_grants_reject_duplicate_and_public_capability(config: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        create_permission_service(config)


def test_permission_plugin_manifest_publishes_versioned_service() -> None:
    assert plugin.manifest.id == "liteyukibot.permissions"
    assert plugin.manifest.version == "0.2.0a2"
    assert plugin.manifest.provides == (PERMISSION_SERVICE,)
