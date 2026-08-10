from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest
from liteyukibot_permissions import Principal
from liteyukibot_profile import PROFILE_SERVICE, ProfileService, ProfileSnapshot, plugin
from liteyukibot_profile.service import SQLiteProfileService, language_value, nickname_value
from liteyukibot_resources import RESOURCE_SERVICE, ResourceField, ResourceService

from liteyukibot import LiteyukiApp
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
from liteyukibot.logging import get_logger


def principal(*, runtime_id: str = "runtime", bot_id: str = "bot", actor_id: str = "user") -> Principal:
    return Principal(runtime_id, bot_id, actor_id)


def event(*, actor_id: str | None = "user", bot_id: str = "bot") -> EventEnvelope:
    return EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id=bot_id,
        type="message",
        conversation=ConversationRef(id="conversation", type="group"),
        actor=None if actor_id is None else ActorRef(id=actor_id),
    )


@pytest.mark.asyncio
async def test_profile_defaults_mutations_and_reopen_persistence(tmp_path: Path) -> None:
    database = tmp_path / "profile.sqlite3"
    service = SQLiteProfileService(database)
    user = principal()
    try:
        assert await service.get(user) == ProfileSnapshot(user)
        await service.set(user, _nickname_field(), "Alice")
        await service.set(user, _language_field(), "en")
        assert await service.get(user) == ProfileSnapshot(user, nickname="Alice", language="en")
        await service.delete(user, _nickname_field())
        assert await service.get(user) == ProfileSnapshot(user, language="en")
    finally:
        await service.close()

    reopened = SQLiteProfileService(database)
    try:
        assert await reopened.get(user) == ProfileSnapshot(user, language="en")
        await reopened.delete(user, _language_field())
        assert await reopened.get(user) == ProfileSnapshot(user)
    finally:
        await reopened.close()


def test_profile_field_converters_are_strict() -> None:
    assert nickname_value(" Alice ") == "Alice"
    assert nickname_value("x" * 32) == "x" * 32
    assert language_value("zh-CN") == "zh-CN"
    with pytest.raises(ValueError, match="1 to 32"):
        nickname_value(" ")
    with pytest.raises(ValueError, match="1 to 32"):
        nickname_value("x" * 33)
    with pytest.raises(ValueError, match="zh-CN"):
        language_value("fr")


@pytest.mark.asyncio
async def test_profile_principals_are_isolated_and_serialized(tmp_path: Path) -> None:
    service = SQLiteProfileService(tmp_path / "profile.sqlite3")
    first = principal(actor_id="first")
    second = principal(bot_id="other", actor_id="first")
    try:
        await service.set(first, _nickname_field(), "Alice")
        await service.set(second, _nickname_field(), "Bob")
        assert await service.get(first) == ProfileSnapshot(first, nickname="Alice")
        assert await service.get(second) == ProfileSnapshot(second, nickname="Bob")
        await asyncio.gather(
            service.set(first, _language_field(), "en"),
            service.set(first, _nickname_field(), "Carol"),
        )
        assert await service.get(first) == ProfileSnapshot(first, nickname="Carol", language="en")
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_profile_plugin_uses_private_storage_and_registers_resource(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        plugins=PluginSettings(
            enabled=(
                "liteyukibot.permissions",
                "liteyukibot.commands",
                "liteyukibot.resources",
                "liteyukibot.profile",
            ),
        ),
    )
    app = LiteyukiApp(settings, logger=get_logger(component="profile-tests"))
    await app.start()
    try:
        resources = cast(ResourceService, app.services.require(RESOURCE_SERVICE))
        profile = cast(ProfileService, app.services.require(PROFILE_SERVICE))
        user = principal()
        assert await profile.get(user) == ProfileSnapshot(user)
        await resources.set(event(), ("profile",), "nickname", "Alice")
        assert await profile.get(user) == ProfileSnapshot(user, nickname="Alice")
        assert (tmp_path / "data" / "plugins" / "liteyukibot.profile" / "profile.sqlite3").is_file()
    finally:
        await app.stop()

    assert plugin.manifest.storage == "private"


@pytest.mark.asyncio
async def test_profile_resource_commands_mutate_data_and_describe_limits(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        plugins=PluginSettings(
            enabled=(
                "liteyukibot.permissions",
                "liteyukibot.commands",
                "liteyukibot.resources",
                "liteyukibot.profile",
                "liteyukibot.essentials",
            ),
        ),
    )
    actions: list[ActionEnvelope] = []

    async def record(action: ActionEnvelope) -> ActionResult:
        actions.append(action)
        return ActionResult(action_id=action.action_id, success=True)

    app = LiteyukiApp(settings, logger=get_logger(component="profile-command-tests"))
    app.events._action_executor = record
    await app.start()
    try:
        for text in ("/profile", "/profile set nickname Alice", "/profile", "/profile delete nickname"):
            await app.events.publish(_message_event(text))
        rendered = [cast(SendMessage, action.action).message.plain_text for action in actions]
        assert rendered == [
            "nickname: \nlanguage: zh-CN",
            "Updated profile.nickname",
            "nickname: Alice\nlanguage: zh-CN",
            "Reset profile.nickname",
        ]

        await app.events.publish(_message_event("/help profile set"))
        help_text = cast(SendMessage, actions[-1].action).message.plain_text
        assert "nickname: Display name; 1 to 32 characters" in help_text
    finally:
        await app.stop()


def _nickname_field() -> ResourceField:
    return ResourceField("nickname", nickname_value)


def _language_field() -> ResourceField:
    return ResourceField("language", language_value)


def _message_event(text: str) -> EventEnvelope:
    return EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="message",
        conversation=ConversationRef(id="conversation", type="group"),
        actor=ActorRef(id="user"),
        message=Message(segments=(Segment(type="text", data={"text": text}),)),
        reply_token="reply",
    )
