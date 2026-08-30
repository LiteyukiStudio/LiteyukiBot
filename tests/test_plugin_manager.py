from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

import pytest
from tomli_w import dumps as dump_toml

import liteyukibot.plugin_manager as plugin_module
from liteyukibot.config import ConfigWorkspace, load_settings
from liteyukibot.plugin_manager import InstalledPlugin, PluginManager, PluginManagerError


def _index(path: Path, artifact: Path, *, bundle_id: str = "example.echo") -> None:
    raw_artifact = artifact.read_bytes()
    document: dict[str, Any] = {
        "schema": 2,
        "bundles": [
            {
                "id": bundle_id,
                "version": "1.0.0",
                "display_name": "Example Echo",
                "summary": "A local Cordis fixture.",
                "publisher": {"id": "example", "name": "Example", "url": "https://example.invalid"},
                "license": {"expression": "MIT"},
                "repository": "https://example.invalid/source",
                "status": "active",
                "dependencies": [],
                "project_id": "example-echo-plugin",
                "facets": [
                    {
                        "runtime_kind": "cordis",
                        "artifacts": [],
                        "wheels": [
                            {
                                "url": str(artifact),
                                "sha256": hashlib.sha256(raw_artifact).hexdigest(),
                                "bytes": len(raw_artifact),
                            }
                        ],
                        "platform": {"systems": [], "machines": [], "pythons": ["3.14"]},
                        "load": {"entry_points": ["example.echo"]},
                        "capabilities": [],
                    }
                ],
            }
        ],
    }
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PluginManager:
    artifact = tmp_path / "example_echo_plugin-1.0.0-py3-none-any.whl"
    artifact.write_bytes(b"fixture wheel")
    index = tmp_path / "index.json"
    _index(index, artifact)
    workspace = ConfigWorkspace(tmp_path / "workspace")
    workspace.initialize()
    monkeypatch.setattr(plugin_module, "_run_uv_install", lambda _paths: None)
    monkeypatch.setattr(plugin_module, "_verify_installed_bundle", lambda _bundle, _facet: None)
    return PluginManager(workspace, index_url=str(index))


def test_empty_schema_one_index_is_supported(tmp_path: Path) -> None:
    index = tmp_path / "index.json"
    index.write_text('{"bundles": [], "schema": 1}\n', encoding="utf-8")
    manager = PluginManager(ConfigWorkspace(tmp_path / "workspace"), index_url=str(index))
    assert manager.fetch_index().bundles == ()


def test_install_stages_verified_wheel_and_activates_entry_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path, monkeypatch)
    records = manager.install("example.echo")

    assert [record.id for record in records] == ["example.echo"]
    settings = load_settings(manager.workspace.path, environ={})
    assert settings.cordis.enabled == ("example.echo",)
    assert manager.installed()[0].enabled is True
    assert manager.workspace.management_directory.joinpath("plugins.json").is_file()


def test_disable_saves_plugin_config_and_enable_restores_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path, monkeypatch)
    manager.install("example.echo")
    config = tomllib.loads(manager.workspace.path.read_text(encoding="utf-8"))
    config["cordis"]["config"] = {"example.echo": {"answer": 42}}
    manager.workspace.path.write_text(dump_toml(config), encoding="utf-8")

    disabled = manager.disable("example.echo")

    assert disabled.enabled is False
    settings = load_settings(manager.workspace.path, environ={})
    assert settings.cordis.enabled == ()
    assert settings.cordis.config == {}
    assert disabled.config == {"example.echo": {"answer": 42}}

    monkeypatch.setattr(plugin_module, "_verify_record_entry_points", lambda _record: None)
    enabled = manager.enable("example.echo")
    assert enabled.enabled is True
    settings = load_settings(manager.workspace.path, environ={})
    assert settings.cordis.enabled == ("example.echo",)
    assert settings.cordis.config == {"example.echo": {"answer": 42}}


def test_plugin_config_cli_surface_updates_only_local_cordis_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path, monkeypatch)
    manager.install("example.echo")

    value = manager.set_config("example.echo", ["nested.answer=42", "enabled=true"])

    assert value == {"example.echo": {"nested": {"answer": 42}, "enabled": True}}
    settings = load_settings(manager.workspace.path, environ={})
    assert settings.cordis.config == {"example.echo": {"nested": {"answer": 42}, "enabled": True}}
    assert manager.config("example.echo") == value

    manager.clear_config("example.echo")

    assert manager.config("example.echo") == {}
    assert load_settings(manager.workspace.path, environ={}).cordis.enabled == ("example.echo",)


def test_enable_rejects_an_uninstalled_state_record(tmp_path: Path) -> None:
    workspace = ConfigWorkspace(tmp_path)
    workspace.initialize()
    manager = PluginManager(workspace, index_url=str(tmp_path / "index.json"))
    with pytest.raises(PluginManagerError, match="not installed"):
        manager.enable("missing.plugin")


def test_disable_rejects_a_bundle_required_by_an_enabled_bundle(tmp_path: Path) -> None:
    workspace = ConfigWorkspace(tmp_path)
    workspace.initialize()
    manager = PluginManager(workspace, index_url=str(tmp_path / "index.json"))
    manager.state.save(
        {
            "library.base": InstalledPlugin(
                "library.base", "1.0.0", "library-base", ("library.base",), (), "local", True, {}
            ),
            "example.echo": InstalledPlugin(
                "example.echo", "1.0.0", "example-echo-plugin", ("example.echo",), ("library.base",), "local", True, {}
            ),
        }
    )

    with pytest.raises(PluginManagerError, match="required by enabled"):
        manager.disable("library.base")


def test_cli_plugin_list_accepts_index_url_after_subcommand(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from liteyukibot import cli

    index = tmp_path / "index.json"
    index.write_text('{"bundles": [], "schema": 1}\n', encoding="utf-8")
    workspace = tmp_path / "workspace"

    assert cli.main(["--workspace", str(workspace), "init"]) == 0
    assert cli.main(["--workspace", str(workspace), "plugin", "list", "--index-url", str(index)]) == 0
    assert "no plugin bundles available" in capsys.readouterr().out


def test_remove_uninstalls_distribution_and_cleans_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path, monkeypatch)
    manager.install("example.echo", enable=False)
    monkeypatch.setattr(plugin_module, "_run_uv_uninstall", lambda _project_id: None)

    manager.remove("example.echo")

    assert manager.installed() == ()
