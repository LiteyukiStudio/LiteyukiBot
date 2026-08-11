"""Safe projection of immutable agent-plugin payloads into framework-owned directories."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from ..plugin_store import ArtifactStore, PluginFacet, PluginStoreError

_MARKER = ".liteyuki-managed.json"
_SCHEMA = 1
RootValidator = Callable[[Path, str], None]


def materialize_projection(
    artifacts: ArtifactStore,
    generation: Path,
    facets: Mapping[str, PluginFacet],
    *,
    runtime_kind: str,
    validate_root: RootValidator,
) -> dict[str, Any]:
    """Extract runtime-owned archives and return a payload-relative projection plan."""

    payload = generation / "payload"
    payload.mkdir(parents=True, exist_ok=True)
    directories: list[str] = []
    root_names: set[str] = set()
    for bundle_id, facet in sorted(facets.items()):
        if facet.runtime_kind != runtime_kind:
            raise PluginStoreError(
                f"{runtime_kind} installer cannot materialize {facet.runtime_kind!r} facet {bundle_id!r}"
            )
        requested = _load_directories(facet.load, runtime_kind)
        if not requested:
            raise PluginStoreError(f"{runtime_kind} facet {bundle_id!r} requires load.directories")
        for artifact in facet.artifacts:
            root = artifacts.extract_zip(artifact.sha256, payload / artifact.sha256)
            for relative in requested:
                candidate = root.joinpath(*relative.parts)
                if not candidate.is_dir():
                    raise PluginStoreError(
                        f"{runtime_kind} facet {bundle_id!r} directory is absent from artifact: {relative.as_posix()}"
                    )
                if candidate.name.startswith(".liteyuki-") or candidate.name in root_names:
                    raise PluginStoreError(
                        f"{runtime_kind} projection has duplicate or reserved plugin root {candidate.name!r}"
                    )
                validate_root(candidate, bundle_id)
                root_names.add(candidate.name)
                directories.append((PurePosixPath(artifact.sha256) / relative).as_posix())
    return {"plugin_directories": directories}


def project_managed_plugins(
    generation: str | Path,
    target: str | Path,
    backups: str | Path,
    *,
    mode: str,
) -> tuple[str, ...]:
    """Atomically project one managed generation into a framework plugin directory."""

    if mode not in {"copy", "symlink"}:
        raise RuntimeError("managed plugin projection_mode must be 'copy' or 'symlink'")
    generation_path = Path(generation).resolve(strict=True)
    target_path = Path(target).resolve()
    backup_root = Path(backups).resolve()
    sources = _projection_sources(generation_path)
    _recover_incomplete_swap(target_path)
    stage = target_path.parent / f".{target_path.name}.liteyuki-next-{_suffix()}"
    try:
        stage.mkdir(parents=True)
        for source in sources:
            destination = stage / source.name
            if mode == "copy":
                shutil.copytree(source, destination, symlinks=False)
            else:
                try:
                    os.symlink(source, destination, target_is_directory=True)
                except OSError as error:
                    raise RuntimeError(f"managed plugin symlink projection failed: {error}") from error
        _write_marker(stage, generation_path.name, tuple(source.name for source in sources))
        _replace_projection(target_path, stage, backup_root)
    except BaseException:
        _remove(stage)
        raise
    return tuple(source.name for source in sources)


def _load_directories(load: Mapping[str, object], runtime_kind: str) -> tuple[PurePosixPath, ...]:
    value = load.get("directories", [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PluginStoreError(f"{runtime_kind} facet load directories must be an array")
    return tuple(_safe_relative(item, f"{runtime_kind} facet load directory") for item in value)


def _projection_sources(generation: Path) -> tuple[Path, ...]:
    plan_path = generation / "load-plan.json"
    try:
        document = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("managed agent generation has an invalid load plan") from error
    if not isinstance(document, Mapping):
        raise RuntimeError("managed agent generation load plan must be an object")
    value = document.get("plugin_directories", [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise RuntimeError("managed agent generation plugin_directories must be an array")
    payload = (generation / "payload").resolve(strict=True)
    sources: list[Path] = []
    names: set[str] = set()
    for raw in value:
        relative = _safe_relative(raw, "managed agent generation directory")
        source = payload.joinpath(*relative.parts).resolve(strict=True)
        try:
            source.relative_to(payload)
        except ValueError as error:
            raise RuntimeError("managed agent generation directory escapes its payload") from error
        if not source.is_dir() or source.name.startswith(".liteyuki-") or source.name in names:
            raise RuntimeError("managed agent generation has an invalid projected plugin root")
        names.add(source.name)
        sources.append(source)
    return tuple(sources)


def _safe_relative(value: object, subject: str) -> PurePosixPath:
    if not isinstance(value, str) or "\\" in value:
        raise PluginStoreError(f"{subject} must be a safe payload-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise PluginStoreError(f"{subject} must be a safe payload-relative path")
    return path


def _replace_projection(target: Path, stage: Path, backups: Path) -> None:
    moved: Path | None = None
    if target.exists() or target.is_symlink():
        if _is_managed_projection(target):
            moved = target.parent / f".{target.name}.liteyuki-previous-{_suffix()}"
        else:
            backups.mkdir(parents=True, exist_ok=True)
            moved = backups / f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{target.name}"
        target.replace(moved)
    try:
        stage.replace(target)
    except BaseException:
        if moved is not None and not target.exists() and not target.is_symlink():
            moved.replace(target)
        raise
    if moved is not None and moved.parent == target.parent:
        _remove(moved)


def _recover_incomplete_swap(target: Path) -> None:
    previous = sorted(target.parent.glob(f".{target.name}.liteyuki-previous-*"))
    if not target.exists() and not target.is_symlink() and previous:
        previous[-1].replace(target)
    for stale in previous[:-1] if not target.exists() else previous:
        _remove(stale)


def _is_managed_projection(target: Path) -> bool:
    if not target.is_dir() or target.is_symlink():
        return False
    marker = target / _MARKER
    try:
        document = json.loads(marker.read_text(encoding="utf-8"))
        declared = document["entries"]
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    if document.get("schema") != _SCHEMA or not isinstance(declared, list) or any(
        not isinstance(entry, str) for entry in declared
    ):
        return False
    actual = {entry.name for entry in target.iterdir() if entry.name != _MARKER}
    return actual == set(declared)


def _write_marker(path: Path, generation_id: str, entries: tuple[str, ...]) -> None:
    (path / _MARKER).write_text(
        json.dumps({"schema": _SCHEMA, "generation": generation_id, "entries": list(entries)}, indent=2) + "\n",
        encoding="utf-8",
    )


def _suffix() -> str:
    return os.urandom(8).hex()


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path, ignore_errors=True)


__all__ = ["materialize_projection", "project_managed_plugins"]
