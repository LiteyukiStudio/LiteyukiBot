from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from liteyukibot_commands import (
    COMMAND_SERVICE,
    ArgumentSpec,
    CommandSchema,
    CommandService,
    CommandSpec,
    OptionSpec,
    integer_value,
)
from liteyukibot_commands.service import create_command_service
from liteyukibot_essentials import plugin, render_status
from liteyukibot_permissions import PERMISSION_SERVICE, PUBLIC, PermissionSnapshot, Principal

import liteyukibot
from liteyukibot import KERNEL_STATUS_SERVICE, LiteyukiApp
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
from liteyukibot.exceptions import PluginError
from liteyukibot.logging import get_logger
from liteyukibot.services import ServiceKey
from liteyukibot.status import KernelStatusSnapshot
from liteyukibot.testing import PluginTestHarness

STATUS_READ = "liteyukibot.status.read"
PROFILE_SERVICE = ServiceKey("liteyukibot.profile", 1)


class PermissionStub:
    def principal(self, event: EventEnvelope) -> Principal | None:
        if event.actor is None:
            return None
        return Principal(event.runtime_id, event.bot_id, event.actor.id)

    def resolve(self, event: EventEnvelope) -> PermissionSnapshot:
        principal = self.principal(event)
        capabilities = {PUBLIC}
        if event.actor is not None and event.actor.id == "operator":
            capabilities.add(STATUS_READ)
        return PermissionSnapshot(principal, frozenset(), frozenset(capabilities))

    def allows(self, event: EventEnvelope, permission: str) -> bool:
        return self.resolve(event).allows(permission)


class StatusStub:
    def snapshot(self) -> KernelStatusSnapshot:
        return KernelStatusSnapshot(
            version="7.0.0a4",
            state="ready",
            uptime_seconds=12.5,
            plugins={"zeta": "ready", "alpha": "stopped"},
            runtimes={"runtime-b": "ready", "runtime-a": "failed"},
            events_outstanding=3,
        )


class ProfileStub:
    def __init__(self, language: str = "en", *, fail: bool = False) -> None:
        self.language = language
        self.fail = fail

    async def get(self, _principal: Principal) -> object:
        if self.fail:
            raise RuntimeError("profile unavailable")
        return self


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


def command_service() -> CommandService:
    return create_command_service({}, PermissionStub(), get_logger(component="essentials-tests"))


@pytest.mark.asyncio
async def test_essentials_registers_and_unregisters_owned_commands(tmp_path: Path) -> None:
    commands = command_service()
    harness = PluginTestHarness(
        plugin,
        root=tmp_path,
        dependencies={COMMAND_SERVICE: commands, KERNEL_STATUS_SERVICE: StatusStub()},
    )

    async with harness:
        registrations = commands.snapshot()
        assert [item.spec.name for item in registrations] == ["help", "status"]
        assert {item.owner for item in registrations} == {"liteyukibot.essentials"}

    assert commands.snapshot() == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["fr", "", 1, None])
async def test_essentials_rejects_invalid_language(tmp_path: Path, language: object) -> None:
    harness = PluginTestHarness(
        plugin,
        root=tmp_path,
        config={"language": language},
        dependencies={COMMAND_SERVICE: command_service(), KERNEL_STATUS_SERVICE: StatusStub()},
    )

    with pytest.raises(PluginError, match="setup failed") as raised:
        await harness.start()

    assert raised.value.__cause__ is not None
    assert "language must be" in str(raised.value.__cause__)


@pytest.mark.asyncio
async def test_essentials_rejects_unknown_configuration(tmp_path: Path) -> None:
    harness = PluginTestHarness(
        plugin,
        root=tmp_path,
        config={"unknown": True},
        dependencies={COMMAND_SERVICE: command_service(), KERNEL_STATUS_SERVICE: StatusStub()},
    )

    with pytest.raises(PluginError, match="setup failed") as raised:
        await harness.start()

    assert raised.value.__cause__ is not None
    assert "unknown essentials config keys" in str(raised.value.__cause__)


@pytest.mark.asyncio
async def test_essentials_uses_optional_profile_language_and_falls_back(tmp_path: Path) -> None:
    commands = command_service()
    harness = PluginTestHarness(
        plugin,
        root=tmp_path,
        dependencies={
            COMMAND_SERVICE: commands,
            KERNEL_STATUS_SERVICE: StatusStub(),
            PROFILE_SERVICE: ProfileStub("en"),
        },
    )
    async with harness:
        subscription = harness._events.subscribe(cast(Any, commands).dispatch, order=-100, name="commands-test")
        result = await harness.publish(message_event("/help"))
        assert result.stopped is True
        assert harness.recorded_actions[-1].action.type == "send_message"
        action = harness.recorded_actions[-1].action
        assert isinstance(action, SendMessage)
        assert action.message.plain_text.startswith("Available commands:")
        harness._events.unsubscribe(subscription)

    failing = PluginTestHarness(
        plugin,
        root=tmp_path / "fallback",
        dependencies={
            COMMAND_SERVICE: command_service(),
            KERNEL_STATUS_SERVICE: StatusStub(),
            PROFILE_SERVICE: ProfileStub(fail=True),
        },
    )
    async with failing:
        subscription = failing._events.subscribe(
            cast(Any, failing.require_service(COMMAND_SERVICE)).dispatch,
            order=-100,
            name="commands-test",
        )
        await failing.publish(message_event("/help"))
        fallback_action = failing.recorded_actions[-1].action
        assert isinstance(fallback_action, SendMessage)
        assert fallback_action.message.plain_text.startswith("可用命令：")
        failing._events.unsubscribe(subscription)


def test_english_status_is_stable_and_sorted() -> None:
    rendered = render_status(StatusStub().snapshot(), language="en")

    assert rendered == "\n".join(
        (
            "LiteyukiBot 7.0.0a4",
            "State: ready",
            "Uptime: 12.500 seconds",
            "Outstanding events: 3",
            "Plugins:",
            "- alpha: stopped",
            "- zeta: ready",
            "Runtimes:",
            "- runtime-a: failed",
            "- runtime-b: ready",
        )
    )


@pytest.mark.asyncio
async def test_three_plugin_topology_filters_help_and_correlates_status(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        plugins=PluginSettings(
            enabled=(
                "liteyukibot.permissions",
                "liteyukibot.commands",
                "liteyukibot.essentials",
            ),
            config={
                "liteyukibot.permissions": {
                    "roles": {"operator": [STATUS_READ]},
                    "grants": [
                        {
                            "runtime_id": "runtime",
                            "bot_id": "bot",
                            "actor_id": "operator",
                            "roles": ["operator"],
                        }
                    ],
                },
                "liteyukibot.commands": {"prefixes": ["/", "//"]},
            },
        ),
    )
    recorded: list[ActionEnvelope] = []

    async def record_action(action: ActionEnvelope) -> ActionResult:
        recorded.append(action)
        return ActionResult(action_id=action.action_id, success=True)

    app = LiteyukiApp(settings, logger=get_logger(component="essentials-integration"))
    app.events._action_executor = record_action
    await app.start()
    commands = cast(CommandService, app.services.require(COMMAND_SERVICE))
    try:
        user_help = message_event("//帮助")
        user_result = await app.events.publish(user_help)
        assert user_result.stopped is True
        user_action = cast(SendMessage, recorded[-1].action)
        assert user_action.message.plain_text == "可用命令：\n//help (//帮助) - 显示可用命令"
        assert recorded[-1].event_id == user_help.id
        assert recorded[-1].runtime_id == user_help.runtime_id
        assert recorded[-1].bot_id == user_help.bot_id
        assert user_action.conversation == user_help.conversation
        assert user_action.reply_token == user_help.reply_token

        before_denial = len(recorded)
        denied_result = await app.events.publish(message_event("/status"))
        assert denied_result.stopped is True
        assert len(recorded) == before_denial

        operator_help = await app.events.publish(message_event("/help", actor_id="operator"))
        assert operator_help.stopped is True
        operator_help_text = cast(SendMessage, recorded[-1].action).message.plain_text
        assert operator_help_text == "\n".join(
            (
                "可用命令：",
                "/help (/帮助) - 显示可用命令",
                "/status (/状态) - 显示内核状态",
            )
        )

        status_event = message_event("/状态", actor_id="operator")
        status_result = await app.events.publish(status_event)
        assert status_result.stopped is True
        status_action = cast(SendMessage, recorded[-1].action)
        assert status_action.message.plain_text.startswith(f"LiteyukiBot {liteyukibot.__version__}\n状态: ready")
        assert "\n插件:\n- liteyukibot.commands: ready\n- liteyukibot.essentials: ready\n" in (
            status_action.message.plain_text
        )
        assert status_action.message.plain_text.endswith("\n运行时:\n- 无")
        assert recorded[-1].event_id == status_event.id
    finally:
        await app.stop()

    assert commands.snapshot() == ()


@pytest.mark.asyncio
async def test_help_resolves_visible_hierarchical_aliases_and_renders_schema(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        plugins=PluginSettings(
            enabled=(
                "liteyukibot.permissions",
                "liteyukibot.commands",
                "liteyukibot.essentials",
            ),
            config={"liteyukibot.essentials": {"language": "en"}},
        ),
    )
    recorded: list[ActionEnvelope] = []

    async def record_action(action: ActionEnvelope) -> ActionResult:
        recorded.append(action)
        return ActionResult(action_id=action.action_id, success=True)

    app = LiteyukiApp(settings, logger=get_logger(component="essentials-help"))
    app.events._action_executor = record_action
    await app.start()
    try:
        commands = cast(CommandService, app.services.require(COMMAND_SERVICE))

        def handler(_invocation: object) -> None:
            return None

        commands.register_many(
            (
                (CommandSpec("plugin", summary="Manage plugins"), handler),
                (
                    CommandSpec(
                        "list",
                        aliases=("ls",),
                        path=("plugin",),
                        summary="List installed plugins",
                        schema=CommandSchema(
                            arguments=(ArgumentSpec("filter", required=False),),
                            options=(
                                OptionSpec("limit", aliases=("n",), converter=integer_value, default=10),
                                OptionSpec("verbose", aliases=("v",), flag=True),
                            ),
                        ),
                    ),
                    handler,
                ),
                (CommandSpec("hidden", permission=STATUS_READ), handler),
            ),
            owner="tests.help",
        )

        root = await app.events.publish(message_event("/help"))
        detail = await app.events.publish(message_event("/help plugin ls"))
        missing = await app.events.publish(message_event("/help hidden"))

        assert root.stopped is True
        assert detail.stopped is True
        assert missing.stopped is True
        assert cast(SendMessage, recorded[0].action).message.plain_text == "\n".join(
            (
                "Available commands:",
                "/help (/帮助) - Show available commands",
                "/plugin - Manage plugins",
            )
        )
        assert cast(SendMessage, recorded[1].action).message.plain_text == "\n".join(
            (
                "/plugin list",
                "Aliases: /plugin ls",
                "List installed plugins",
                "Usage: /plugin list [FILTER] [--limit LIMIT] [--verbose]",
                "Arguments:",
                "- filter (optional)",
                "Options:",
                "- --limit, -n (optional)",
                "- --verbose, -v (optional)",
            )
        )
        assert cast(SendMessage, recorded[2].action).message.plain_text == "Command not found"
    finally:
        await app.stop()


def test_essentials_manifest_declares_optional_profile_service() -> None:
    assert plugin.manifest.id == "liteyukibot.essentials"
    assert plugin.manifest.version == "0.2.0a2"
    assert plugin.manifest.provides == ()
    assert tuple(item.key for item in plugin.manifest.requires) == (
        COMMAND_SERVICE,
        KERNEL_STATUS_SERVICE,
        PROFILE_SERVICE,
    )
    assert PERMISSION_SERVICE not in tuple(item.key for item in plugin.manifest.requires)
