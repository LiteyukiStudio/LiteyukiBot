from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
from liteyukibot_commands import (
    COMMAND_SERVICE,
    CommandInvocation,
    CommandService,
    CommandSpec,
    plugin,
)
from liteyukibot_permissions import PERMISSION_SERVICE, PUBLIC, PermissionSnapshot, Principal

from liteyukibot import LiteyukiApp
from liteyukibot.config import AppSettings, CoreSettings, PluginSettings
from liteyukibot.events import (
    ActorRef,
    ConversationRef,
    EventEnvelope,
    HandlerResult,
    Message,
    Segment,
    SendMessage,
)
from liteyukibot.exceptions import PluginError, ServiceError
from liteyukibot.logging import get_logger
from liteyukibot.testing import PluginTestHarness

ADMIN = "tests.admin"


class PermissionStub:
    def principal(self, event: EventEnvelope) -> Principal | None:
        if event.actor is None:
            return None
        return Principal(event.runtime_id, event.bot_id, event.actor.id)

    def resolve(self, event: EventEnvelope) -> PermissionSnapshot:
        principal = self.principal(event)
        capabilities = {PUBLIC}
        if event.actor is not None and event.actor.id == "operator":
            capabilities.add(ADMIN)
        return PermissionSnapshot(principal, frozenset(), frozenset(capabilities))

    def allows(self, event: EventEnvelope, permission: str) -> bool:
        return self.resolve(event).allows(permission)


def message_event(text: str, *, actor_id: str = "user") -> EventEnvelope:
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


def make_harness(
    tmp_path: Path,
    *,
    config: Mapping[str, Any] | None = None,
) -> PluginTestHarness:
    return PluginTestHarness(
        plugin,
        root=tmp_path,
        config=config,
        dependencies={PERMISSION_SERVICE: PermissionStub()},
    )


@pytest.mark.asyncio
async def test_command_router_dispatches_alias_and_preserves_arguments(tmp_path: Path) -> None:
    observed: list[tuple[str, str, str, str]] = []
    async with make_harness(tmp_path) as harness:
        service = cast(CommandService, harness.require_service(COMMAND_SERVICE))

        async def echo(invocation: CommandInvocation) -> HandlerResult:
            observed.append(
                (
                    invocation.command,
                    invocation.invoked_as,
                    invocation.prefix,
                    invocation.raw_arguments,
                )
            )
            return invocation.reply(f"echo: {invocation.raw_arguments}")

        service.register(CommandSpec("echo", aliases=("E",)), echo, owner="tests.echo")
        result = await harness.publish(message_event("  /e Hello  world  "))

        assert result.stopped is True
        assert observed == [("echo", "e", "/", "Hello  world  ")]
        sent = cast(SendMessage, harness.recorded_actions[0].action)
        assert sent.message.plain_text == "echo: Hello  world  "
        assert sent.reply_token == "reply-token"


@pytest.mark.asyncio
async def test_command_router_uses_longest_prefix_and_ignores_unknown_input(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []
    async with make_harness(tmp_path, config={"prefixes": ["/", "//"]}) as harness:
        service = cast(CommandService, harness.require_service(COMMAND_SERVICE))
        service.register(
            CommandSpec("echo"),
            lambda invocation: calls.append((invocation.command, invocation.prefix)),
            owner="tests.echo",
        )

        matched = await harness.publish(message_event("//echo"))
        spaced = await harness.publish(message_event("/ echo"))
        unknown = await harness.publish(message_event("/missing"))
        plain = await harness.publish(message_event("echo"))

        assert matched.stopped is True
        assert calls == [("echo", "//")]
        assert spaced.stopped is False
        assert unknown.stopped is False
        assert plain.stopped is False


@pytest.mark.asyncio
async def test_command_registration_is_atomic_and_explicitly_owned(tmp_path: Path) -> None:
    async with make_harness(tmp_path) as harness:
        service = cast(CommandService, harness.require_service(COMMAND_SERVICE))
        def handler(_invocation: CommandInvocation) -> None:
            return None

        first = service.register(CommandSpec("alpha", aliases=("a",)), handler, owner="tests")

        with pytest.raises(ValueError, match="already registered"):
            service.register_many(
                (
                    (CommandSpec("beta"), handler),
                    (CommandSpec("gamma", aliases=("A",)), handler),
                ),
                owner="tests",
            )

        assert service.snapshot() == (first,)
        assert service.unregister(first) is True
        assert service.unregister(first) is False
        assert service.snapshot() == ()


@pytest.mark.asyncio
async def test_recognized_denied_and_failed_commands_stop_propagation(tmp_path: Path) -> None:
    calls: list[str] = []
    async with make_harness(tmp_path) as harness:
        service = cast(CommandService, harness.require_service(COMMAND_SERVICE))

        def denied(_invocation: Any) -> None:
            calls.append("denied")

        def failed(_invocation: Any) -> None:
            calls.append("failed")
            raise RuntimeError("secret failure")

        def invalid(_invocation: Any) -> str:
            calls.append("invalid")
            return "not a HandlerResult"

        service.register(CommandSpec("denied", permission=ADMIN), denied, owner="tests")
        service.register(CommandSpec("failed"), failed, owner="tests")
        service.register(CommandSpec("invalid"), invalid, owner="tests")  # type: ignore[arg-type]

        denied_result = await harness.publish(message_event("/denied"))
        failed_result = await harness.publish(message_event("/failed"))
        invalid_result = await harness.publish(message_event("/invalid"))

        assert denied_result.stopped is True
        assert failed_result.stopped is True
        assert invalid_result.stopped is True
        assert calls == ["failed", "invalid"]
        assert harness.recorded_actions == ()


@pytest.mark.asyncio
async def test_visible_commands_are_sorted_and_permission_filtered(tmp_path: Path) -> None:
    async with make_harness(tmp_path) as harness:
        service = cast(CommandService, harness.require_service(COMMAND_SERVICE))
        def handler(_invocation: CommandInvocation) -> None:
            return None

        service.register(CommandSpec("zeta"), handler, owner="tests")
        service.register(CommandSpec("admin", permission=ADMIN), handler, owner="tests")
        service.register(CommandSpec("alpha"), handler, owner="tests")

        user_commands = service.visible(message_event("unused"))
        operator_commands = service.visible(message_event("unused", actor_id="operator"))

        assert [item.spec.name for item in user_commands] == ["alpha", "zeta"]
        assert [item.spec.name for item in operator_commands] == ["admin", "alpha", "zeta"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"unknown": True}, "unknown command config keys"),
        ({"prefixes": "/"}, "must be a sequence"),
        ({"prefixes": []}, "must not be empty"),
        ({"prefixes": [""]}, "must be non-empty"),
        ({"prefixes": ["/", "/"]}, "duplicates an earlier prefix"),
        ({"prefixes": [1]}, "must be a string"),
    ],
)
async def test_command_plugin_rejects_invalid_configuration(
    tmp_path: Path,
    config: dict[str, object],
    message: str,
) -> None:
    harness = make_harness(tmp_path, config=config)

    with pytest.raises(PluginError, match="setup failed") as raised:
        await harness.start()

    assert raised.value.__cause__ is not None
    assert message in str(raised.value.__cause__)


def test_command_spec_rejects_invalid_and_duplicate_tokens() -> None:
    with pytest.raises(ValueError, match="without whitespace"):
        CommandSpec("bad name")
    with pytest.raises(ValueError, match="duplicate command"):
        CommandSpec("echo", aliases=("ECHO",))
    with pytest.raises(ValueError, match="permission"):
        CommandSpec("echo", permission="")


@pytest.mark.asyncio
async def test_command_plugin_service_is_removed_on_stop(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    async with harness:
        assert harness.require_service(COMMAND_SERVICE) is not None

    with pytest.raises(ServiceError, match="unavailable"):
        harness.require_service(COMMAND_SERVICE)


def test_command_plugin_manifest_declares_permission_dependency() -> None:
    assert plugin.manifest.id == "liteyukibot.commands"
    assert plugin.manifest.version == "0.1.0a1"
    assert plugin.manifest.provides == (COMMAND_SERVICE,)
    assert tuple(item.key for item in plugin.manifest.requires) == (PERMISSION_SERVICE,)


@pytest.mark.asyncio
async def test_installed_permission_and_command_plugins_start_as_real_topology(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        plugins=PluginSettings(
            enabled=("liteyukibot.permissions", "liteyukibot.commands"),
            config={"liteyukibot.commands": {"prefixes": ["/"]}},
        ),
    )
    app = LiteyukiApp(settings, logger=get_logger(component="commands-integration"))

    await app.start()
    try:
        service = cast(CommandService, app.services.require(COMMAND_SERVICE))

        def ping(_invocation: CommandInvocation) -> None:
            return None

        service.register(CommandSpec("ping"), ping, owner="tests.integration")
        result = await app.events.publish(message_event("/ping"))

        assert result.stopped is True
        assert app.services.provider_for(PERMISSION_SERVICE) == "liteyukibot.permissions"
        assert app.services.provider_for(COMMAND_SERVICE) == "liteyukibot.commands"
    finally:
        await app.stop()
