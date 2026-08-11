"""AstrBot ownership of managed plugin-root validation and materialization."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from liteyukibot.plugin_store import ArtifactStore, PluginFacet, PluginStoreError
from liteyukibot.runtime.projection import materialize_projection


class AstrBotFacetInstaller:
    """Build an AstrBot plugin-root projection plan from immutable archives."""

    def materialize(
        self,
        artifacts: ArtifactStore,
        generation: Path,
        facets: Mapping[str, PluginFacet],
    ) -> dict[str, Any]:
        return materialize_projection(
            artifacts,
            generation,
            facets,
            runtime_kind="astrbot",
            validate_root=_validate_root,
        )


def _validate_root(root: Path, bundle_id: str) -> None:
    if not ((root / "main.py").is_file() or (root / f"{root.name}.py").is_file()):
        raise PluginStoreError(f"AstrBot facet {bundle_id!r} plugin root has no main module: {root.name}")
    if any(path.is_file() for path in root.rglob("requirements.txt")):
        raise PluginStoreError(
            f"AstrBot facet {bundle_id!r} contains requirements.txt; declare hash-verified wheels instead"
        )


__all__ = ["AstrBotFacetInstaller"]
