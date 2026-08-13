from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from liteyukibot_commands import COMMAND_SERVICE, CommandService
from liteyukibot_commands.service import create_command_service
from liteyukibot_permissions import PERMISSION_SERVICE, PUBLIC, PermissionSnapshot, Principal
from liteyukibot_resources import (
    RESOURCE_SERVICE,
    ResourceError,
    ResourceField,
    ResourceProvider,
    ResourceSpec,
    plugin,
)
from liteyukibot_resources.service import create_resource_service

from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope
from liteyukibot.i18n import I18N_SERVICE, Translator
from liteyukibot.logging import get_logger
from liteyukibot.resource_packs import ResourceCatalog
from liteyukibot.testing import PluginTestHarness


def event(*, actor_id: str | None = "user") -> EventEnvelope:
    return EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="message",
        conversation=ConversationRef(id="group", type="group"),
        actor=None if actor_id is None else ActorRef(id=actor_id),
    )


class PermissionStub:
    def principal(self, item: EventEnvelope) -> Principal | None:
        if item.actor is None:
            return None
        return Principal(item.runtime_id, item.bot_id, item.actor.id)

    def resolve(self, item: EventEnvelope) -> PermissionSnapshot:
        principal = self.principal(item)
        capabilities = {PUBLIC}
        if item.actor is not None:
            capabilities.add("profile.manage")
        return PermissionSnapshot(principal, frozenset(), frozenset(capabilities))

    def allows(self, _event: EventEnvelope, capability: str) -> bool:
        return capability == "profile.manage"


class DenyingPermissionStub(PermissionStub):
    def allows(self, _event: EventEnvelope, _capability: str) -> bool:
        return False


class Provider(ResourceProvider):
    def __init__(self) -> None:
        self.values = {"user": "Alice"}

    async def inspect(self, principal: Principal, field: ResourceField) -> object:
        return self.values.get(principal.actor_id, "")

    async def set(self, principal: Principal, field: ResourceField, value: object) -> None:
        self.values[principal.actor_id] = cast(str, value)

    async def delete(self, principal: Principal, field: ResourceField) -> None:
        self.values.pop(principal.actor_id, None)


def specification() -> ResourceSpec:
    return ResourceSpec(
        "profile",
        summary="User profile",
        fields=(
            ResourceField(
                "nickname",
                str,
                description="Display name",
                inspect_capability="profile.manage",
                set_capability="profile.manage",
                delete_capability="profile.manage",
            ),
        ),
    )


def command_service() -> CommandService:
    return create_command_service({}, PermissionStub(), get_logger(component="resources-tests"))


def translator() -> Translator:
    return Translator.from_resources(ResourceCatalog.load(".", plugin_packs=plugin.manifest.resource_packs), "zh-CN")[0]


@pytest.mark.asyncio
async def test_resource_plugin_provides_service_and_removes_it_on_stop(tmp_path: Path) -> None:
    harness = PluginTestHarness(
        plugin,
        root=tmp_path,
        dependencies={
            PERMISSION_SERVICE: PermissionStub(),
            COMMAND_SERVICE: command_service(),
            I18N_SERVICE: translator(),
        },
    )
    async with harness:
        assert harness.require_service(RESOURCE_SERVICE) is not None


@pytest.mark.asyncio
async def test_resource_service_reads_writes_and_deletes_current_principal() -> None:
    service = create_resource_service(PermissionStub(), command_service(), translator())
    provider = Provider()
    service.register(specification(), provider, owner="test")

    current = event()
    assert await service.inspect(current, ("profile",)) == {"nickname": "Alice"}
    await service.set(current, ("profile",), "nickname", "Bob")
    assert await service.inspect(current, ("profile",)) == {"nickname": "Bob"}
    await service.delete(current, ("profile",), "nickname")
    assert await service.inspect(current, ("profile",)) == {"nickname": ""}


@pytest.mark.asyncio
async def test_resource_service_requires_capability_for_other_actor() -> None:
    service = create_resource_service(PermissionStub(), command_service(), translator())
    provider = Provider()
    service.register(specification(), provider, owner="test")

    current = event()
    await service.set(current, ("profile",), "nickname", "Bob", actor_id="other")
    assert await service.inspect(current, ("profile",), actor_id="other") == {"nickname": "Bob"}


@pytest.mark.asyncio
async def test_resource_service_fails_closed_for_other_actor() -> None:
    service = create_resource_service(DenyingPermissionStub(), command_service(), translator())
    service.register(specification(), Provider(), owner="test")

    with pytest.raises(ResourceError, match="not authorized"):
        await service.set(event(), ("profile",), "nickname", "Bob", actor_id="other")


def test_resource_registration_is_atomic_and_path_stable() -> None:
    service = create_resource_service(PermissionStub(), command_service(), translator())
    provider = Provider()
    profile = specification()
    duplicate = ResourceSpec("PROFILE", fields=(ResourceField("language", str),))

    with pytest.raises(ValueError, match="already registered"):
        service.register_many(((profile, provider), (duplicate, provider)), owner="test")

    assert service.snapshot() == ()
    registration = service.register(profile, provider, owner="test")
    assert service.resolve(("PrOfIlE",)) == registration
    assert service.unregister(registration) is True
    assert service.resolve(("profile",)) is None


@pytest.mark.asyncio
async def test_resource_service_rejects_anonymous_and_invalid_operations() -> None:
    service = create_resource_service(PermissionStub(), command_service(), translator())
    service.register(specification(), Provider(), owner="test")

    with pytest.raises(ResourceError, match="resource not found"):
        await service.inspect(event(actor_id="user"), ("missing",))

    with pytest.raises(ResourceError, match="require an actor"):
        await service.inspect(event(actor_id=None), ("profile",))
