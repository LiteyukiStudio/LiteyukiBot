from __future__ import annotations

import json
from pathlib import Path

import pytest

import liteyukibot.cli as cli_module
from liteyukibot.config import ConfigurationError, ConfigWorkspace, load_settings
from liteyukibot.instances import InstancePaths, normalize_instance_name


def test_named_instance_overlay_follows_config_but_precedes_environment_and_cli(tmp_path: Path) -> None:
    primary = tmp_path / "liteyuki.toml"
    primary.write_text("config_version = 5\n[core]\nqueue_capacity = 10\n", encoding="utf-8")
    extra = tmp_path / "extra.toml"
    extra.write_text("[core]\nqueue_capacity = 15\n", encoding="utf-8")
    overlay = tmp_path / "instance.toml"
    overlay.write_text("[core]\nqueue_capacity = 20\n", encoding="utf-8")

    settings = load_settings(
        primary,
        config_paths=(extra,),
        instance_config_paths=(overlay,),
        environ={"LITEYUKI__CORE__QUEUE_CAPACITY": "30"},
        cli_overrides=("core.queue_capacity=40",),
    )

    assert settings.core.queue_capacity == 40


@pytest.mark.parametrize("path", ("config_version = 4\n", "[core]\ndata_dir = 'outside'\n", "[logging]\nfile = 'x'\n"))
def test_instance_overlay_cannot_redirect_isolated_storage(tmp_path: Path, path: str) -> None:
    primary = tmp_path / "liteyuki.toml"
    primary.write_text("config_version = 5\n", encoding="utf-8")
    overlay = tmp_path / "instance.toml"
    overlay.write_text(path, encoding="utf-8")

    with pytest.raises(ConfigurationError, match="instance configuration cannot set"):
        load_settings(primary, instance_config_paths=(overlay,), environ={})


def test_named_instance_derives_all_kernel_storage(tmp_path: Path) -> None:
    workspace = ConfigWorkspace(tmp_path)
    workspace.initialize()
    paths = InstancePaths.from_workspace(workspace, "staging")

    settings = paths.apply_storage(load_settings(workspace.path, environ={}))

    assert settings.core.data_dir == tmp_path / ".liteyuki" / "instances" / "staging" / "data"
    assert settings.core.cache_dir == tmp_path / ".liteyuki" / "instances" / "staging" / "cache"
    assert settings.logging.file == tmp_path / ".liteyuki" / "instances" / "staging" / "logs" / "kernel.log"
    assert paths.daemon_descriptor == tmp_path / ".liteyuki" / "instances" / "staging" / "daemon.json"


def test_default_instance_keeps_configured_storage(tmp_path: Path) -> None:
    workspace = ConfigWorkspace(tmp_path)
    workspace.initialize(data_dir="bot-data", cache_dir="bot-cache")
    paths = InstancePaths.from_workspace(workspace, "default")
    settings = load_settings(workspace.path, environ={})

    assert paths.apply_storage(settings) is settings
    assert settings.core.data_dir == tmp_path / "bot-data"
    assert settings.core.cache_dir == tmp_path / "bot-cache"


@pytest.mark.parametrize("value", ("UPPER", "two_words", "spaces here", "", "-first"))
def test_instance_name_validation(value: str) -> None:
    with pytest.raises(ValueError, match="instance name"):
        normalize_instance_name(value)


def test_cli_config_show_uses_named_instance_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ConfigWorkspace(tmp_path).initialize()

    assert cli_module.main(["--workspace", str(tmp_path), "--instance", "dev", "config", "show"]) == 0

    rendered = json.loads(capsys.readouterr().out)
    assert rendered["core"]["data_dir"] == str(tmp_path / ".liteyuki" / "instances" / "dev" / "data")
