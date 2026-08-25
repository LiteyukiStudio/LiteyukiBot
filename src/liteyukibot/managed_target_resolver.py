"""Root composition adapter from installed bridges to managed plugin targets."""

from __future__ import annotations

from .bridge_contracts import (
    BridgeSupportGrade,
    ManagedFacetProbe,
    ManagedPluginTarget,
)
from .broker.service import BridgeCatalog


def resolve_managed_plugin_target(kind: str) -> ManagedPluginTarget | None:
    """Resolve a discovered bridge into the neutral plugin-install boundary.

    Args:
        kind: Stable runtime kind requested by plugin installation.

    Returns:
        Neutral target candidate, or `None` when no bridge owns the kind.

    Notes:
        Discovery remains lazy and uncached. Composition owns the policy that
        only stable bridges with installer and import probe metadata are
        eligible for managed plugin generations.
    """
    bridge = BridgeCatalog().discover().get(kind)
    if bridge is None:
        return None
    installer = bridge.facet_installer
    eligible = bridge.grade is BridgeSupportGrade.STABLE and installer is not None and bridge.probe_module is not None
    return ManagedPluginTarget(
        kind=bridge.kind,
        distribution=bridge.distribution,
        eligible=eligible,
        facet_installer=installer,
        probe_module=bridge.probe_module,
        facet_probe=installer if isinstance(installer, ManagedFacetProbe) else None,
    )


__all__ = ["resolve_managed_plugin_target"]
