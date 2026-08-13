"""Adapter-runtime ownership of immutable adapter wheel generation loading."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from liteyukibot.plugin_store import ArtifactStore, PluginFacet, PluginStoreError


class AdapterFacetInstaller:
    """Restrict a managed generation to explicitly resolved adapter entry points."""

    def materialize(
        self,
        _artifacts: ArtifactStore,
        _generation: Path,
        facets: Mapping[str, PluginFacet],
    ) -> dict[str, Any]:
        adapters: list[str] = []
        for bundle_id, facet in sorted(facets.items()):
            if facet.runtime_kind != "adapter":
                raise PluginStoreError(
                    f"adapter installer cannot materialize {facet.runtime_kind!r} facet {bundle_id!r}"
                )
            declared = _adapter_list(facet.load)
            if not declared:
                raise PluginStoreError(f"adapter facet {bundle_id!r} requires adapter entry points")
            if facet.artifacts:
                raise PluginStoreError("adapter facets must install adapter distributions as verified wheels")
            adapters.extend(declared)
        if len(set(adapters)) != len(adapters):
            raise PluginStoreError("adapter load plan cannot repeat adapter entry points")
        return {"adapters": adapters}


def _adapter_list(load: Mapping[str, object]) -> tuple[str, ...]:
    value = load.get("adapters", [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PluginStoreError("adapter facet load 'adapters' must be an array")
    adapters = tuple(str(item) for item in value)
    if any(not item or item != item.strip() for item in adapters):
        raise PluginStoreError("adapter facet load 'adapters' contains an invalid entry point name")
    return adapters


__all__ = ["AdapterFacetInstaller"]
