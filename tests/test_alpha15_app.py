from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from liteyukibot_kernel import ActorRef, ConversationRef, EventEnvelope

from liteyukibot import LiteyukiApp
from liteyukibot import cli as cli_module
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
