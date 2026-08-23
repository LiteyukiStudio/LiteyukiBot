"""Runtime-owned conversion of immutable plugin artifacts into load plans."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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


class RuntimeFacetProbe(Protocol):
    """Optional framework-owned startup probe for a materialized generation."""

    def probe_command(self, python: Path, generation: Path) -> Sequence[str]:
        """Return the isolated command that must succeed before activation.

        Args:
            python: Generation virtual environment interpreter.
            generation: Materialized generation root.

        Returns:
            Non-empty child process command for the framework startup probe.
        """


__all__ = ["RuntimeFacetInstaller", "RuntimeFacetProbe"]
