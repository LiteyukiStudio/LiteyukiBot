"""Protocol-neutral contracts for managed plugin generation materialization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from .plugin_store import ArtifactStore, PluginFacet


class ManagedFacetInstaller(Protocol):
    """Package hook that materializes immutable plugin facets into a generation."""

    def materialize(
        self,
        artifacts: ArtifactStore,
        generation: Path,
        facets: Mapping[str, PluginFacet],
    ) -> dict[str, Any]:
        """Create package-owned payload files and return a JSON-safe load plan.

        Args:
            artifacts: Immutable artifact store.
            generation: Managed generation root.
            facets: Facets selected for the target package.

        Returns:
            The target package's JSON-safe load plan.
        """
        ...


class ManagedFacetProbe(Protocol):
    """Optional package-owned startup probe for a materialized generation."""

    def probe_command(self, python: Path, generation: Path) -> Sequence[str]:
        """Return the isolated command that must succeed before activation.

        Args:
            python: Generation virtual-environment interpreter.
            generation: Managed generation root.

        Returns:
            Non-empty child-process command for the startup probe.
        """
        ...


__all__ = ["ManagedFacetInstaller", "ManagedFacetProbe"]
