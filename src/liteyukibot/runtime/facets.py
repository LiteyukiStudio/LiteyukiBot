"""Runtime-owned conversion of immutable plugin artifacts into load plans."""

from __future__ import annotations

from ..managed_plugins import ManagedFacetInstaller, ManagedFacetProbe

RuntimeFacetInstaller = ManagedFacetInstaller
RuntimeFacetProbe = ManagedFacetProbe

__all__ = ["RuntimeFacetInstaller", "RuntimeFacetProbe"]
