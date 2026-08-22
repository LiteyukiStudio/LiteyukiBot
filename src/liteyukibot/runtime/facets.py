"""Runtime-owned conversion of immutable plugin artifacts into load plans."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from ..plugin_store import ArtifactStore, PluginFacet


class RuntimeFacetInstaller(Protocol):
    """Framework package hook used by the kernel-managed generation builder."""

    def materialize(
        self,
        artifacts: ArtifactStore,
        generation: Path,
        facets: Mapping[str, PluginFacet],
    ) -> dict[str, Any]:
        """Create framework-owned payload files and return a JSON-safe load plan.

        Args:
            artifacts: The artifacts value used by the operation.
            generation: Positive protocol or deployment generation.
            facets: The facets value used by the operation.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """


__all__ = ["RuntimeFacetInstaller"]
