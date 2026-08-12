from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest
from liteyukibot_runtime_v6.facets import V6FacetInstaller

from liteyukibot.plugin_store import ArtifactSpec, ArtifactStore, PluginFacet, PluginStoreError


def _artifact(tmp_path: Path) -> tuple[ArtifactStore, str]:
    archive = tmp_path / "plugin.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("plugins/example.py", "VALUE = 1\n")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    store = ArtifactStore(tmp_path)
    store.import_file(archive, digest)
    return store, digest


def test_v6_facet_materializes_archives_into_a_payload_relative_load_plan(tmp_path: Path) -> None:
    store, digest = _artifact(tmp_path)
    facet = PluginFacet(
        "v6",
        (ArtifactSpec("https://example.invalid/plugin.zip", digest),),
        load={"modules": ["example.plugin"], "directories": ["plugins"]},
    )

    plan = V6FacetInstaller().materialize(store, tmp_path / "generation", {"example.echo": facet})

    assert plan == {"modules": ["example.plugin"], "directories": [f"{digest}/plugins"]}
    assert (tmp_path / "generation" / "payload" / digest / "plugins" / "example.py").is_file()


def test_v6_facet_rejects_missing_or_unsafe_load_directories(tmp_path: Path) -> None:
    store, digest = _artifact(tmp_path)
    artifact = ArtifactSpec("https://example.invalid/plugin.zip", digest)

    with pytest.raises(PluginStoreError, match="absent"):
        V6FacetInstaller().materialize(
            store,
            tmp_path / "generation",
            {"example.echo": PluginFacet("v6", (artifact,), load={"directories": ["missing"]})},
        )
    with pytest.raises(PluginStoreError, match="safe relative"):
        V6FacetInstaller().materialize(
            store,
            tmp_path / "generation",
            {"example.echo": PluginFacet("v6", (artifact,), load={"directories": ["../escape"]})},
        )
