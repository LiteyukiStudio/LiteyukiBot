from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest
from liteyukibot_runtime_nonebot.facets import NoneBotFacetInstaller

from liteyukibot.json_value import JsonValue
from liteyukibot.plugin_store import ArtifactSpec, ArtifactStore, PluginFacet, PluginStoreError


def _artifact(tmp_path: Path) -> tuple[ArtifactStore, str]:
    archive = tmp_path / "plugin.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("plugins/example.py", "VALUE = 1\n")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    store = ArtifactStore(tmp_path)
    store.import_file(archive, digest)
    return store, digest


def test_nonebot_facet_materializes_payload_relative_load_plan(tmp_path: Path) -> None:
    store, digest = _artifact(tmp_path)
    facet = PluginFacet(
        "nonebot",
        (ArtifactSpec("https://example.invalid/plugin.zip", digest),),
        load={"plugins": ["example.plugin"], "directories": ["plugins"]},
    )

    plan = NoneBotFacetInstaller().materialize(store, tmp_path / "generation", {"example.echo": facet})

    expected: dict[str, JsonValue] = {
        "plugins": ["example.plugin"],
        "directories": [f"{digest}/plugins"],
    }
    assert plan == expected
    assert (tmp_path / "generation" / "payload" / digest / "plugins" / "example.py").is_file()


def test_nonebot_facet_rejects_missing_directory(tmp_path: Path) -> None:
    store, digest = _artifact(tmp_path)
    artifact = ArtifactSpec("https://example.invalid/plugin.zip", digest)

    with pytest.raises(PluginStoreError, match="absent"):
        NoneBotFacetInstaller().materialize(
            store,
            tmp_path / "generation",
            {"example.echo": PluginFacet("nonebot", (artifact,), load={"directories": ["missing"]})},
        )
