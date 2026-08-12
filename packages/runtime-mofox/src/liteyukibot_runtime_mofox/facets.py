"""Neo-MoFox ownership of managed plugin-root validation and materialization."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from liteyukibot.plugin_store import ArtifactStore, PluginFacet, PluginStoreError
from liteyukibot.runtime.projection import materialize_projection


class MoFoxFacetInstaller:
    """Build a Neo-MoFox plugin-root projection plan from immutable archives."""

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
            runtime_kind="mofox",
            validate_root=_validate_root,
        )


def _validate_root(root: Path, bundle_id: str) -> None:
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise PluginStoreError(f"MoFox facet {bundle_id!r} has an invalid manifest.json") from error
    if not isinstance(manifest, dict):
        raise PluginStoreError(f"MoFox facet {bundle_id!r} manifest.json must be an object")
    dependencies = manifest.get("python_dependencies", [])
    if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
        raise PluginStoreError(f"MoFox facet {bundle_id!r} manifest python_dependencies must be an array of strings")
    if dependencies:
        raise PluginStoreError(
            f"MoFox facet {bundle_id!r} declares python_dependencies; declare hash-verified wheels instead"
        )


__all__ = ["MoFoxFacetInstaller"]
