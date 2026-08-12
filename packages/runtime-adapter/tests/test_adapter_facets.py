from __future__ import annotations

from pathlib import Path

import pytest
from liteyukibot_runtime_adapter.facets import AdapterFacetInstaller

from liteyukibot.plugin_store import ArtifactSpec, PluginFacet, PluginStoreError

_WHEEL = ArtifactSpec("https://example.invalid/adapter.whl", "a" * 64)
_ARCHIVE = ArtifactSpec("https://example.invalid/adapter.zip", "b" * 64)


def test_adapter_facet_generates_entry_point_load_plan(tmp_path: Path) -> None:
    plan = AdapterFacetInstaller().materialize(
        None,  # type: ignore[arg-type]
        tmp_path / "generation",
        {"example.onebot": PluginFacet("adapter", (), wheels=(_WHEEL,), load={"adapters": ["onebot-v11"]})},
    )

    assert plan == {"adapters": ["onebot-v11"]}


def test_adapter_facet_requires_wheels_not_archives(tmp_path: Path) -> None:
    facet = PluginFacet("adapter", (_ARCHIVE,), load={"adapters": ["example"]})

    with pytest.raises(PluginStoreError, match="verified wheels"):
        AdapterFacetInstaller().materialize(None, tmp_path / "generation", {"example": facet})  # type: ignore[arg-type]
