from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

import liteyukibot.cli as cli_module
from liteyukibot.config import ConfigUpgradeRequired, ConfigurationError, ConfigWorkspace, load_settings


def test_workspace_init_creates_current_valid_template(tmp_path: Path) -> None:
    workspace = ConfigWorkspace(tmp_path)

    path = workspace.initialize(payload_exclude_runtimes=("mofox",))

    assert path == tmp_path / "liteyuki.toml"
    assert load_settings(path, environ={}).config_version == 1
    assert load_settings(path, environ={}).logging.payload_exclude_runtimes == ("mofox",)


def test_workspace_init_rejects_invalid_logging_values_without_writing(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ConfigWorkspace(tmp_path).initialize(payload_mode="everything")

    assert not (tmp_path / "liteyuki.toml").exists()


def test_outdated_workspace_config_is_backed_up_and_blocks_start(tmp_path: Path) -> None:
    config = tmp_path / "liteyuki.toml"
    config.write_text("[core]\nqueue_capacity = 1\n", encoding="utf-8")

    with pytest.raises(ConfigUpgradeRequired, match="manual upgrade"):
        ConfigWorkspace(tmp_path).prepare()

    backups = list((tmp_path / ".liteyuki" / "config-backups").glob("*/liteyuki.toml"))
    assert len(backups) == 1
    template = tmp_path / ".liteyuki" / "config-upgrades" / "liteyuki.v1.toml"
    assert "config_version = 1" in template.read_text(encoding="utf-8")


def test_workspace_upgrade_is_idempotent_until_explicit_refresh(tmp_path: Path) -> None:
    config = tmp_path / "liteyuki.toml"
    config.write_text("config_version = 0\n[core]\nqueue_capacity = 1\n", encoding="utf-8")
    workspace = ConfigWorkspace(tmp_path)

    with pytest.raises(ConfigUpgradeRequired):
        workspace.prepare()
    with pytest.raises(ConfigUpgradeRequired, match="existing template"):
        workspace.prepare()
    assert len(list((tmp_path / ".liteyuki" / "config-backups").glob("*/liteyuki.toml"))) == 1

    with pytest.raises(ConfigUpgradeRequired):
        workspace.upgrade(refresh=True)
    assert len(list((tmp_path / ".liteyuki" / "config-backups").glob("*/liteyuki.toml"))) == 2


def test_future_workspace_config_is_not_backed_up(tmp_path: Path) -> None:
    config = tmp_path / "liteyuki.toml"
    config.write_text("config_version = 2\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="newer than this kernel"):
        ConfigWorkspace(tmp_path).prepare()
    assert not (tmp_path / ".liteyuki").exists()


def test_regular_workspace_without_config_requires_initialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ConfigWorkspace, "is_docker", staticmethod(lambda: False))

    with pytest.raises(ConfigurationError, match="liteyuki init"):
        ConfigWorkspace(tmp_path).prepare()
    assert not (tmp_path / "liteyuki.toml").exists()


def test_docker_workspace_without_config_initializes_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ConfigWorkspace, "is_docker", staticmethod(lambda: True))

    path = ConfigWorkspace(tmp_path).prepare()

    assert path == tmp_path / "liteyuki.toml"
    assert path.is_file()
    settings = load_settings(path, environ={})
    assert settings.plugins.enabled == ()
    assert settings.runtimes == {}


def test_cli_init_noninteractive_writes_project_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert cli_module.main(["init", "--non-interactive"]) == 0
    assert (tmp_path / "liteyuki.toml").is_file()
