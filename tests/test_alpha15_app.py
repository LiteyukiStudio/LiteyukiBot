from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest
from liteyukibot_kernel import ActorRef, ConversationRef, EventEnvelope

from liteyukibot import LiteyukiApp
from liteyukibot import cli as cli_module
from liteyukibot.app import AppState
from liteyukibot.config import ConfigWorkspace, load_settings
from liteyukibot.features.resources import RESOURCE_SERVICE, ResourceService


@pytest.mark.asyncio
async def test_default_workspace_starts_all_required_features(tmp_path: Path) -> None:
    config = ConfigWorkspace(tmp_path).initialize()
    app = LiteyukiApp(load_settings(config, environ={}), resource_workspace=tmp_path)

    with pytest.raises(RuntimeError, match="not accepting events"):
        await app.publish(
            EventEnvelope(
                runtime_id="test",
                adapter="test",
                bot_id="bot",
                type="message",
                conversation=ConversationRef(id="user", type="private"),
            )
        )
    await app.start()
    try:
        assert app.status()["state"] == "ready"
        assert app.status()["features"] == {
            "commands": "ready",
            "essentials": "ready",
            "permissions": "ready",
            "profile": "ready",
            "resources": "ready",
        }
        assert app.onebot is None
    finally:
        await app.stop()

    assert app.status()["state"] == "stopped"
    assert app.status()["features"] == {
        "commands": "stopped",
        "essentials": "stopped",
        "permissions": "stopped",
        "profile": "stopped",
        "resources": "stopped",
    }
    assert app.services.get(RESOURCE_SERVICE) is None


@pytest.mark.asyncio
async def test_stop_waits_for_an_in_progress_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = ConfigWorkspace(tmp_path).initialize()
    app = LiteyukiApp(load_settings(config, environ={}), resource_workspace=tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed_cordis() -> None:
        entered.set()
        await release.wait()

    monkeypatch.setattr(app, "_start_cordis", delayed_cordis)
    starting = asyncio.create_task(app.start())
    await entered.wait()
    stopping = asyncio.create_task(app.stop())
    await asyncio.sleep(0)

    assert app.state.value == "starting"
    release.set()
    await asyncio.gather(starting, stopping)

    assert app.state.value == "stopped"
    assert app.status()["accepting_events"] is False
    assert app.events.closed


@pytest.mark.asyncio
async def test_stop_recovers_when_a_lifecycle_operation_reference_is_missing(tmp_path: Path) -> None:
    config = ConfigWorkspace(tmp_path).initialize()

    for state in (AppState.STARTING, AppState.STOPPING):
        app = LiteyukiApp(load_settings(config, environ={}), resource_workspace=tmp_path)
        app.state = state

        await app.stop()

        assert app.state is AppState.STOPPED
        assert app.events.closed


@pytest.mark.asyncio
async def test_custom_profile_database_parent_is_created(tmp_path: Path) -> None:
    config = ConfigWorkspace(tmp_path).initialize(profile={"database": "nested/profile.sqlite3"})
    app = LiteyukiApp(load_settings(config, environ={}), resource_workspace=tmp_path)

    await app.start()
    try:
        assert (tmp_path / "nested" / "profile.sqlite3").is_file()
    finally:
        await app.stop()


def test_onebot_account_key_is_preserved_as_runtime_identity(tmp_path: Path) -> None:
    config = ConfigWorkspace(tmp_path).initialize(
        onebot={
            "v11": {
                "accounts": {
                    "qq-main": {
                        "implementation": "snowluma",
                        "self_id": "42",
                        "ws_url": "ws://127.0.0.1:3001/",
                    }
                }
            }
        }
    )

    settings = load_settings(config, environ={})
    assert tuple(settings.onebot.v11.accounts) == ("qq-main",)


def test_cli_check_rejects_invalid_onebot_transport(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ConfigWorkspace(tmp_path).initialize(
        onebot={
            "v11": {
                "accounts": {
                    "qq-main": {
                        "implementation": "snowluma",
                        "self_id": "42",
                        "ws_url": "ws://example.invalid/",
                    }
                }
            }
        }
    )

    assert cli_module.main(["--workspace", str(tmp_path), "check"]) == 2
    assert "loopback" in capsys.readouterr().err


def test_cli_check_rejects_non_string_onebot_token(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ConfigWorkspace(tmp_path).initialize(
        onebot={
            "v11": {
                "accounts": {
                    "qq-main": {
                        "implementation": "snowluma",
                        "self_id": "42",
                        "ws_url": "ws://127.0.0.1:3001/",
                        "access_token": 123,
                    }
                }
            }
        }
    )

    assert cli_module.main(["--workspace", str(tmp_path), "check"]) == 2
    assert "access_token must be a string" in capsys.readouterr().err


def test_config_rejects_configuration_for_disabled_cordis_plugin(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not enabled"):
        ConfigWorkspace(tmp_path).initialize(cordis_config={"example.plugin": {"enabled": True}})


@pytest.mark.asyncio
async def test_resources_persist_profile_fields(tmp_path: Path) -> None:
    config = ConfigWorkspace(tmp_path).initialize()
    app = LiteyukiApp(load_settings(config, environ={}), resource_workspace=tmp_path)
    event = EventEnvelope(
        runtime_id="qq-main",
        adapter="onebot.v11",
        bot_id="42",
        type="message.private.friend",
        conversation=ConversationRef(id="1001", type="private"),
        actor=ActorRef(id="1001"),
    )

    await app.start()
    try:
        resources = cast(ResourceService, app.services.require(RESOURCE_SERVICE))
        await resources.set(event, ("profile",), "nickname", "Alice")
        assert await resources.inspect(event, ("profile",)) == {"nickname": "Alice", "language": "zh-CN"}
        await resources.delete(event, ("profile",), "nickname")
        assert await resources.inspect(event, ("profile",)) == {"nickname": "", "language": "zh-CN"}
    finally:
        await app.stop()
