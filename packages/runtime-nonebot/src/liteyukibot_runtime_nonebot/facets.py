"""NoneBot ownership of immutable plugin archive materialization."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from liteyukibot.bridge_contracts import ManagedArtifactStore, ManagedFacet
from liteyukibot.plugin_store import PluginStoreError

_MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")


class NoneBotFacetInstaller:
    """Materialize NoneBot plugin archives beneath a managed generation payload."""

    def materialize(
        self,
        artifacts: ManagedArtifactStore,
        generation: Path,
        facets: Mapping[str, ManagedFacet],
    ) -> dict[str, Any]:
        """Materialize the none bot facet installer operation.

        Args:
            artifacts: The artifacts value used by the operation.
            generation: Positive protocol or deployment generation.
            facets: The facets value used by the operation.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        payload = generation / "payload"
        payload.mkdir(parents=True, exist_ok=True)
        plugins: list[str] = []
        directories: list[str] = []
        for bundle_id, facet in sorted(facets.items()):
            if facet.runtime_kind != "nonebot":
                raise PluginStoreError(
                    f"NoneBot installer cannot materialize {facet.runtime_kind!r} facet {bundle_id!r}"
                )
            facet_plugins = _module_list(facet.load)
            facet_directories = _directory_list(facet.load)
            if not facet_plugins and not facet_directories:
                raise PluginStoreError(f"NoneBot facet {bundle_id!r} requires plugins or directories")
            for artifact in facet.artifacts:
                artifacts.extract_zip(artifact.sha256, payload / artifact.sha256)
                for directory in facet_directories:
                    candidate = payload / artifact.sha256 / directory
                    if not candidate.is_dir():
                        raise PluginStoreError(
                            f"NoneBot facet {bundle_id!r} directory is absent from artifact: {directory}"
                        )
                    directories.append((PurePosixPath(artifact.sha256) / directory).as_posix())
            plugins.extend(facet_plugins)
        if len(set(plugins)) != len(plugins) or len(set(directories)) != len(directories):
            raise PluginStoreError("NoneBot load plan cannot repeat plugins or directories")
        return {"plugins": plugins, "directories": directories}

    def probe_command(self, python: Path, generation: Path) -> tuple[str, ...]:
        """Return the isolated NoneBot startup probe for one generation.

        Args:
            python: Generation virtual environment interpreter.
            generation: Materialized generation root.

        Returns:
            Command that initializes NoneBot and loads the complete plan.
        """
        return (str(python), "-m", "liteyukibot_runtime_nonebot.probe", str(generation))


def _module_list(load: Mapping[str, object]) -> tuple[str, ...]:
    """Implement the module list operation for the component.

    Args:
        load: The load value used by the operation.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_module_list`. It delegates to `get`, `any`, `fullmatch`
        while keeping intermediate state local to the owning operation.
    """
    value = load.get("plugins", [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PluginStoreError("NoneBot facet load 'plugins' must be an array of module names")
    plugins = tuple(str(item) for item in value)
    if any(not _MODULE.fullmatch(item) for item in plugins):
        raise PluginStoreError("NoneBot facet load 'plugins' contains an invalid module name")
    return plugins


def _directory_list(load: Mapping[str, object]) -> tuple[PurePosixPath, ...]:
    """Implement the directory list operation for the component.

    Args:
        load: The load value used by the operation.

    Returns:
        The `tuple[PurePosixPath, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_directory_list`. It delegates to `get`, `is_absolute`,
        `any`, `append` while keeping intermediate state local to the owning operation.
    """
    value = load.get("directories", [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PluginStoreError("NoneBot facet load 'directories' must be an array")
    directories: list[PurePosixPath] = []
    for raw in value:
        if not isinstance(raw, str):
            raise PluginStoreError("NoneBot facet load directories must contain strings")
        path = PurePosixPath(raw)
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise PluginStoreError("NoneBot facet load directory must be a safe relative path")
        directories.append(path)
    return tuple(directories)


__all__ = ["NoneBotFacetInstaller"]
