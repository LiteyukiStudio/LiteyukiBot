from __future__ import annotations

import json
from pathlib import Path

import pytest

from liteyukibot.plugin_store import PluginStoreError
from liteyukibot.runtime.projection import project_managed_plugins


def _generation(tmp_path: Path, generation_id: str, plugin_name: str = "example") -> Path:
    generation = tmp_path / generation_id
    digest = "a" * 64
    plugin = generation / "payload" / digest / plugin_name
    plugin.mkdir(parents=True)
    (plugin / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
    (generation / "load-plan.json").write_text(
        json.dumps({"plugin_directories": [f"{digest}/{plugin_name}"]}), encoding="utf-8"
    )
    return generation


def test_copy_projection_backs_up_unmanaged_directory_and_replaces_managed_generation(tmp_path: Path) -> None:
    first = _generation(tmp_path, "first")
    second = _generation(tmp_path, "second", "replacement")
    target = tmp_path / "state" / "plugins"
    (target / "legacy").mkdir(parents=True)
    (target / "legacy" / "plugin.py").write_text("legacy\n", encoding="utf-8")
    backups = tmp_path / "state" / "managed-plugin-backups"

    assert project_managed_plugins(first, target, backups, mode="copy") == ("example",)
    assert (target / "example" / "main.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    saved = tuple(backups.iterdir())
    assert len(saved) == 1
    assert (saved[0] / "legacy" / "plugin.py").read_text(encoding="utf-8") == "legacy\n"

    assert project_managed_plugins(second, target, backups, mode="copy") == ("replacement",)
    assert not (target / "example").exists()
    assert (target / "replacement" / "main.py").is_file()
    assert tuple(backups.iterdir()) == saved


def test_projection_rejects_unsafe_load_plan_and_unknown_mode(tmp_path: Path) -> None:
    generation = _generation(tmp_path, "generation")
    (generation / "load-plan.json").write_text(json.dumps({"plugin_directories": ["../escape"]}), encoding="utf-8")

    with pytest.raises(PluginStoreError, match="safe payload-relative"):
        project_managed_plugins(generation, tmp_path / "target", tmp_path / "backups", mode="copy")
    with pytest.raises(RuntimeError, match="projection_mode"):
        project_managed_plugins(generation, tmp_path / "target", tmp_path / "backups", mode="invalid")


def test_empty_managed_generation_atomically_clears_an_earlier_projection(tmp_path: Path) -> None:
    first = _generation(tmp_path, "first")
    empty = tmp_path / "empty"
    (empty / "payload").mkdir(parents=True)
    (empty / "load-plan.json").write_text('{"plugin_directories": []}', encoding="utf-8")
    target = tmp_path / "state" / "plugins"
    backups = tmp_path / "state" / "managed-plugin-backups"

    project_managed_plugins(first, target, backups, mode="copy")
    assert project_managed_plugins(empty, target, backups, mode="copy") == ()

    assert not (target / "example").exists()
    assert (target / ".liteyuki-managed.json").is_file()
    assert not backups.exists()
