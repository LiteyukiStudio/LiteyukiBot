"""v6 ownership of immutable plugin archive materialization."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from liteyukibot.plugin_store import ArtifactStore, PluginFacet, PluginStoreError

_MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")


class V6FacetInstaller:
    """Materialize v6 source archives below one generation's immutable payload."""

    def materialize(
        self,
        artifacts: ArtifactStore,
        generation: Path,
        facets: Mapping[str, PluginFacet],
    ) -> dict[str, Any]:
        payload = generation / "payload"
        payload.mkdir(parents=True, exist_ok=True)
        modules: list[str] = []
        directories: list[str] = []
        for bundle_id, facet in sorted(facets.items()):
            if facet.runtime_kind != "v6":
                raise PluginStoreError(f"v6 installer cannot materialize {facet.runtime_kind!r} facet {bundle_id!r}")
            facet_modules = _module_list(facet.load, "modules")
            facet_directories = _directory_list(facet.load)
            if not facet_modules and not facet_directories:
                raise PluginStoreError(f"v6 facet {bundle_id!r} requires modules or directories")
            for artifact in facet.artifacts:
                artifacts.extract_zip(artifact.sha256, payload / artifact.sha256)
                for directory in facet_directories:
                    candidate = payload / artifact.sha256 / directory
                    if not candidate.is_dir():
                        raise PluginStoreError(f"v6 facet {bundle_id!r} directory is absent from artifact: {directory}")
                    directories.append((PurePosixPath(artifact.sha256) / directory).as_posix())
            modules.extend(facet_modules)
        if len(set(modules)) != len(modules) or len(set(directories)) != len(directories):
            raise PluginStoreError("v6 load plan cannot repeat modules or directories")
        return {"modules": modules, "directories": directories}


def _module_list(load: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = load.get(key, [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PluginStoreError(f"v6 facet load {key!r} must be an array of module names")
    modules = tuple(str(item) for item in value)
    if any(not _MODULE.fullmatch(item) for item in modules):
        raise PluginStoreError(f"v6 facet load {key!r} contains an invalid module name")
    return modules


def _directory_list(load: Mapping[str, object]) -> tuple[PurePosixPath, ...]:
    value = load.get("directories", [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PluginStoreError("v6 facet load 'directories' must be an array")
    directories: list[PurePosixPath] = []
    for raw in value:
        if not isinstance(raw, str):
            raise PluginStoreError("v6 facet load directories must contain strings")
        path = PurePosixPath(raw)
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise PluginStoreError("v6 facet load directory must be a safe relative path")
        directories.append(path)
    return tuple(directories)


__all__ = ["V6FacetInstaller"]
