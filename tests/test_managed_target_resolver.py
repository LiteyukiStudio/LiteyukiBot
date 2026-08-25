from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from liteyukibot.bridge_contracts import (
    BridgeDefinition,
    BridgeLauncher,
    BridgeSupportGrade,
    ManagedArtifactStore,
    ManagedFacet,
    ManagedFacetProbe,
)
from liteyukibot.broker.service import BridgeCatalog
from liteyukibot.managed_target_resolver import resolve_managed_plugin_target


class _Installer:
    def materialize(
        self,
        _artifacts: ManagedArtifactStore,
        _generation: Path,
        _facets: Mapping[str, ManagedFacet],
    ) -> dict[str, Any]:
        return {}

    def probe_command(self, _python: Path, _generation: Path) -> Sequence[str]:
        return ("probe",)


def _definition(grade: BridgeSupportGrade) -> BridgeDefinition:
    return BridgeDefinition(
        kind="nonebot",
        grade=grade,
        distribution="liteyukibot-v7-runtime-nonebot",
        launch=cast(BridgeLauncher, lambda _settings, _bridge_id, _token: None),
        facet_installer=_Installer(),
        probe_module="liteyukibot_runtime_nonebot",
    )


def test_composition_resolves_stable_managed_target_with_explicit_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BridgeCatalog, "discover", lambda _self: {"nonebot": _definition(BridgeSupportGrade.STABLE)})

    target = resolve_managed_plugin_target("nonebot")

    assert target is not None
    assert target.eligible is True
    assert target.facet_installer is not None
    assert target.facet_probe is cast(ManagedFacetProbe, target.facet_installer)


def test_composition_keeps_installed_but_ineligible_target_distinct_from_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        BridgeCatalog,
        "discover",
        lambda _self: {"nonebot": _definition(BridgeSupportGrade.EXPERIMENTAL)},
    )

    target = resolve_managed_plugin_target("nonebot")

    assert target is not None and target.eligible is False
    assert resolve_managed_plugin_target("missing") is None
