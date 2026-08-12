from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from liteyukibot_runtime_astrbot.facets import AstrBotFacetInstaller
from liteyukibot_runtime_astrbot.host import _prepare_managed_plugins

from liteyukibot.plugin_store import ArtifactSpec, ArtifactStore, PluginFacet, PluginStoreError


def _artifact(tmp_path: Path, *, requirements: bool = False) -> tuple[ArtifactStore, str]:
    archive = tmp_path / "plugin.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("plugin/main.py", "VALUE = 1\n")
        if requirements:
            value.writestr("plugin/requirements.txt", "requests>=2\n")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    store = ArtifactStore(tmp_path)
    store.import_file(archive, digest)
    return store, digest


def test_astrbot_facet_materializes_plugin_roots_and_projects_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, digest = _artifact(tmp_path)
    facet = PluginFacet(
        "astrbot",
        (ArtifactSpec("https://example.invalid/plugin.zip", digest),),
        load={"directories": ["plugin"]},
    )
    generation = tmp_path / "generation"

    plan = AstrBotFacetInstaller().materialize(store, generation, {"example.plugin": facet})
    assert plan == {
        "plugin_directories": [f"{digest}/plugin"]
    }
    (generation / "load-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setenv("LITEYUKI_RUNTIME_GENERATION_DIR", str(generation))
    _prepare_managed_plugins(tmp_path / "state" / "astrbot", {"projection_mode": "copy"})

    assert (tmp_path / "state" / "astrbot" / "data" / "plugins" / "plugin" / "main.py").is_file()


def test_astrbot_facet_rejects_upstream_requirements_file(tmp_path: Path) -> None:
    store, digest = _artifact(tmp_path, requirements=True)
    facet = PluginFacet(
        "astrbot",
        (ArtifactSpec("https://example.invalid/plugin.zip", digest),),
        load={"directories": ["plugin"]},
    )

    with pytest.raises(PluginStoreError, match="hash-verified wheels"):
        AstrBotFacetInstaller().materialize(store, tmp_path / "generation", {"example.plugin": facet})


def test_astrbot_projection_requires_string_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generation = tmp_path / "generation"
    (generation / "payload").mkdir(parents=True)
    (generation / "load-plan.json").write_text('{"plugin_directories": []}', encoding="utf-8")
    monkeypatch.setenv("LITEYUKI_RUNTIME_GENERATION_DIR", str(generation))

    with pytest.raises(ValueError, match="projection_mode"):
        _prepare_managed_plugins(tmp_path / "state" / "astrbot", {"projection_mode": 1})
