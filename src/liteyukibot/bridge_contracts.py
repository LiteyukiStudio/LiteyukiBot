"""Protocol-neutral contracts shared by bridge and managed-plugin owners."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .config.models import AppSettings


class BridgeLauncher(Protocol):
    """An installed bridge package's process-local launch entry point."""

    def __call__(self, settings: AppSettings, bridge_id: str, token: str) -> Awaitable[None] | None:
        """Launch one configured bridge instance.

        Args:
            settings: Validated application settings.
            bridge_id: Stable identifier for the bridge.
            token: Authentication token presented at the boundary.

        Returns:
            Optional awaitable that completes when the bridge stops.
        """
        ...


class BridgeSupportGrade(StrEnum):
    """Release qualification declared by an installed bridge distribution."""

    EXPERIMENTAL = "experimental"
    STABLE = "stable"
    MIXED = "mixed"


class ManagedArtifact(Protocol):
    """Verified artifact identity exposed to a managed facet installer."""

    @property
    def sha256(self) -> str:
        """Return the immutable artifact digest.

        Returns:
            Lowercase SHA-256 digest of the verified artifact.
        """
        ...


class ManagedArtifactStore(Protocol):
    """Narrow artifact operation required by managed facet installers."""

    def extract_zip(self, digest: str, destination: str | Path) -> Path:
        """Extract one verified archive beneath the requested destination.

        Args:
            digest: Lowercase digest of an artifact already in the store.
            destination: Empty destination directory for extracted files.

        Returns:
            Resolved extraction destination.
        """
        ...


class ManagedFacet(Protocol):
    """Plugin facet fields required during package-owned materialization."""

    @property
    def runtime_kind(self) -> str:
        """Return the owning runtime kind.

        Returns:
            Stable runtime kind that owns this facet.
        """
        ...

    @property
    def artifacts(self) -> tuple[ManagedArtifact, ...]:
        """Return verified archives materialized by the runtime package.

        Returns:
            Immutable artifact identities in declared order.
        """
        ...

    @property
    def load(self) -> Mapping[str, object]:
        """Return the validated package-owned load plan.

        Returns:
            JSON-safe package-owned load configuration.
        """
        ...


class ManagedFacetInstaller(Protocol):
    """Package hook that materializes immutable plugin facets."""

    def materialize(
        self,
        artifacts: ManagedArtifactStore,
        generation: Path,
        facets: Mapping[str, ManagedFacet],
    ) -> dict[str, Any]:
        """Create package-owned payload files and return a JSON-safe load plan.

        Args:
            artifacts: Narrow verified-artifact extraction boundary.
            generation: Managed generation root.
            facets: Enabled facets selected for the target package.

        Returns:
            Target package's JSON-safe load plan.
        """
        ...


@runtime_checkable
class ManagedFacetProbe(Protocol):
    """Optional package-owned startup probe for a materialized generation."""

    def probe_command(self, python: Path, generation: Path) -> Sequence[str]:
        """Return the isolated command that must succeed before activation.

        Args:
            python: Generation virtual-environment interpreter.
            generation: Materialized generation root.

        Returns:
            Non-empty child-process command for the startup probe.
        """
        ...


@dataclass(frozen=True, slots=True)
class BridgeDefinition:
    """Package-owned metadata and launcher for one bridge kind."""

    kind: str
    grade: BridgeSupportGrade
    distribution: str
    launch: BridgeLauncher
    facet_installer: ManagedFacetInstaller | None = None
    probe_module: str | None = None


__all__ = [
    "BridgeDefinition",
    "BridgeLauncher",
    "BridgeSupportGrade",
    "ManagedArtifact",
    "ManagedArtifactStore",
    "ManagedFacet",
    "ManagedFacetInstaller",
    "ManagedFacetProbe",
]
