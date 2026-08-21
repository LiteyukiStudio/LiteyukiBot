from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

import liteyukibot.cli as cli_module
from liteyukibot import __version__
from liteyukibot.config import ConfigUpgradeRequired, ConfigurationError, ConfigWorkspace, load_settings


def test_workspace_init_creates_current_valid_template(tmp_path: Path) -> None:
    workspace = ConfigWorkspace(tmp_path)

    path = workspace.initialize()

    assert path == tmp_path / "liteyuki.toml"
    assert load_settings(path, environ={}).config_version == 6
    assert load_settings(path, environ={}).logging.payload_exclude_runtimes == ()


def test_workspace_init_rejects_invalid_logging_values_without_writing(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ConfigWorkspace(tmp_path).initialize(payload_mode="everything")

    assert not (tmp_path / "liteyuki.toml").exists()


def test_outdated_workspace_config_is_backed_up_and_blocks_start(tmp_path: Path) -> None:
    config = tmp_path / "liteyuki.toml"
    original = "[core]\nqueue_capacity = 1\nobsolete_field = true\n"
    config.write_text(original, encoding="utf-8")

    with pytest.raises(ConfigUpgradeRequired, match="manual upgrade"):
        ConfigWorkspace(tmp_path).prepare()

    backups = list((tmp_path / ".liteyuki" / "config-backups").glob("*/liteyuki.toml"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == original
    assert backups[0].stat().st_mode & 0o200 == 0
    assert config.read_text(encoding="utf-8") == original
    template = tmp_path / ".liteyuki" / "config-upgrades" / "liteyuki.v6.toml"
    assert "config_version = 6" in template.read_text(encoding="utf-8")
    instructions = (tmp_path / ".liteyuki" / "config-upgrades" / "README.md").read_text(encoding="utf-8")
    assert "did not modify your existing configuration" in instructions


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
    config.write_text("config_version = 7\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="newer than this kernel"):
        ConfigWorkspace(tmp_path).prepare()
    assert not (tmp_path / ".liteyuki").exists()


@pytest.mark.parametrize("version", (0, 1, 2, 3, 4, 5))
def test_every_pre_v6_version_creates_recovery_material_without_validating_old_fields(
    tmp_path: Path, version: int
) -> None:
    config = tmp_path / "liteyuki.toml"
    original = f"config_version = {version}\nobsolete = {{ nested = true }}\n"
    config.write_text(original, encoding="utf-8")

    with pytest.raises(ConfigUpgradeRequired, match="manual upgrade"):
        ConfigWorkspace(tmp_path).prepare()

    backup = next((tmp_path / ".liteyuki" / "config-backups").glob("*/liteyuki.toml"))
    assert backup.read_text(encoding="utf-8") == original
    assert config.read_text(encoding="utf-8") == original


def test_v5_workspace_requires_manual_migration_without_rewriting_active_config(tmp_path: Path) -> None:
    config = tmp_path / "liteyuki.toml"
    original = "config_version = 5\n[legacy]\nvalue = true\n"
    config.write_text(original, encoding="utf-8")

    with pytest.raises(ConfigUpgradeRequired, match="migration_required"):
        ConfigWorkspace(tmp_path).prepare()

    assert config.read_text(encoding="utf-8") == original


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


def test_cli_init_uses_explicit_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "instance"

    assert cli_module.main(["--workspace", str(workspace), "init", "--non-interactive"]) == 0

    assert (workspace / "liteyuki.toml").is_file()


def test_cli_version_option_exits_successfully(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli_module.main(["--version"])

    assert raised.value.code == 0
    assert capsys.readouterr().out.strip() == __version__
