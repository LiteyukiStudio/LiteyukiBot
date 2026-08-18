from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast

import pytest
from liteyukibot_commands import COMMAND_SERVICE, CommandInvocation, CommandService, CommandSpec
from liteyukibot_profile.service import ProfileMigrationRequiredError, SQLiteProfileService

from liteyukibot import AuthorizationContext, LiteyukiApp
from liteyukibot.config import AppSettings, CordisSettings, CoreSettings, PluginSettings

BUSINESS_PLUGINS = (
    "liteyukibot.permissions",
    "liteyukibot.commands",
    "liteyukibot.resources",
    "liteyukibot.profile",
    "liteyukibot.essentials",
)


def _authorization() -> AuthorizationContext:
    return AuthorizationContext(event_id="event-1", runtime_id="runtime", bot_id="bot", actor_id="user")


@pytest.mark.asyncio
async def test_native_business_tools_are_registered_and_bound_to_current_context(tmp_path: Path) -> None:
    app = LiteyukiApp(
        AppSettings(
            core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
            plugins=PluginSettings(enabled=BUSINESS_PLUGINS),
        )
    )
    await app.start()
    try:
        handlers = app.plugins.tool_handlers
        expected = {
            "liteyukibot.permissions.check",
            "liteyukibot.resources.inspect",
            "liteyukibot.resources.set",
            "liteyukibot.resources.delete",
            "liteyukibot.profile.inspect",
            "liteyukibot.profile.set",
            "liteyukibot.profile.delete",
            "liteyukibot.essentials.help",
            "liteyukibot.essentials.status",
        }
        assert expected <= set(handlers)
        authorization = _authorization()
        profile_set = handlers["liteyukibot.profile.set"][2]
        profile_inspect = handlers["liteyukibot.profile.inspect"][2]
        assert await profile_set(authorization, {"field": "nickname", "value": "Alice"}) == {"updated": True}
        assert await profile_inspect(authorization, {}) == {"nickname": "Alice", "language": "zh-CN"}
    finally:
        await app.stop()


@pytest.mark.asyncio
async def test_help_tool_filters_commands_by_authorization_context(tmp_path: Path) -> None:
    app = LiteyukiApp(
        AppSettings(
            core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
            plugins=PluginSettings(enabled=BUSINESS_PLUGINS),
        )
    )
    await app.start()
    try:
        commands = cast(CommandService, app.services.require(COMMAND_SERVICE))

        async def hidden_command(_invocation: CommandInvocation) -> None:
            return None

        commands.register(CommandSpec("restricted", permission="tests.restricted.read"), hidden_command, owner="tests")
        help_tool = app.plugins.tool_handlers["liteyukibot.essentials.help"][2]
        result = await help_tool(_authorization(), {})
        assert isinstance(result, dict)
        commands_result = result.get("commands")
        assert isinstance(commands_result, list)
        assert all(item.get("path") != ["restricted"] for item in commands_result if isinstance(item, dict))
    finally:
        await app.stop()


@pytest.mark.asyncio
async def test_cordis_business_chain_uses_the_same_tools_and_services(tmp_path: Path) -> None:
    app = LiteyukiApp(
        AppSettings(
            core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
            cordis=CordisSettings(enabled=tuple(reversed(BUSINESS_PLUGINS))),
        )
    )
    await app.start()
    try:
        host = app._cordis_host
        assert host is not None
        assert {item.id for item in host.tool_declarations} >= {
            "liteyukibot.resources.inspect",
            "liteyukibot.profile.inspect",
        }
        profile_set = host.tool_handlers["liteyukibot.profile.set"]
        assert await profile_set(_authorization(), {"field": "language", "value": "en"}) == {"updated": True}
    finally:
        await app.stop()


@pytest.mark.asyncio
async def test_profile_schema_one_is_a_hard_cut(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 1")
    with pytest.raises(ProfileMigrationRequiredError, match="^migration_required$"):
        SQLiteProfileService(database)


@pytest.mark.asyncio
async def test_business_v1_configuration_fails_with_stable_diagnostic(tmp_path: Path) -> None:
    app = LiteyukiApp(
        AppSettings(
            core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
            plugins=PluginSettings(
                enabled=("liteyukibot.permissions",),
                config={"liteyukibot.permissions": {"schema_version": 1}},
            ),
        )
    )
    with pytest.raises(Exception, match="migration_required"):
        await app.start()
