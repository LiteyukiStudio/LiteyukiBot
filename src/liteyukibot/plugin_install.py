"""Build and activate one isolated runtime plugin generation."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from .plugin_sources import PluginSource, PluginSourceStore
from .plugin_store import (
    ArtifactStore,
    PlatformTarget,
    PluginBundle,
    PluginFacet,
    PluginIndex,
    PluginStoreError,
    RuntimeGeneration,
    RuntimeGenerationStore,
)
from .runtime import RuntimeCatalog, RuntimePlugin

CommandRunner = Callable[[list[str]], None]


@dataclass(frozen=True, slots=True)
class PluginInstallResult:
    """The immutable generation activated by one successful installation."""

    source_id: str
    generation: RuntimeGeneration


class PluginInstallationService:
    """Resolve source metadata into a runtime-owned, independently restartable generation."""

    def __init__(self, workspace: str | Path, *, run: CommandRunner | None = None) -> None:
        self.workspace = Path(workspace).resolve()
        self.sources = PluginSourceStore(self.workspace)
        self.artifacts = ArtifactStore(self.workspace)
        self.generations = RuntimeGenerationStore(self.workspace)
        self._run = run or _run_command

    def install(
        self,
        bundle_id: str,
        *,
        runtime_id: str,
        runtime_kind: str,
        source_id: str | None = None,
    ) -> PluginInstallResult:
        source, index = self._resolve_source(bundle_id, source_id)
        bundles = _resolve_bundles(index, bundle_id)
        target = PlatformTarget.current()
        facets = {bundle.id: bundle.facet_for(runtime_kind, target) for bundle in bundles}
        runtime = self._require_runtime(runtime_kind)
        generation_id = self.generations.new_generation_id()
        generation_path = self.generations.path_for(runtime_id, generation_id)
        try:
            generation_path.mkdir(parents=True)
            for facet in facets.values():
                for artifact in (*facet.artifacts, *facet.wheels):
                    self.artifacts.fetch(artifact)
            self._create_environment(generation_path, runtime, facets)
            installer = runtime.facet_installer
            if installer is None:
                raise AssertionError("managed runtime installer is required")
            load_plan = installer.materialize(self.artifacts, generation_path, facets)
            generation = RuntimeGeneration(
                id=generation_id,
                runtime_id=runtime_id,
                runtime_kind=runtime_kind,
                created_at=_utc_now(),
                target=target,
                bundles=tuple(bundle.id for bundle in bundles),
                artifacts=tuple(
                    artifact.sha256
                    for facet in facets.values()
                    for artifact in (*facet.artifacts, *facet.wheels)
                ),
                load_plan=load_plan,
            )
            self.generations.write(generation)
            self.generations.activate(runtime_id, generation_id)
        except BaseException:
            shutil.rmtree(generation_path, ignore_errors=True)
            _prune_empty_generation_parents(generation_path)
            raise
        return PluginInstallResult(source.id, generation)

    def _resolve_source(self, bundle_id: str, source_id: str | None) -> tuple[PluginSource, PluginIndex]:
        if source_id is not None:
            index = self.sources.fetch(source_id, refresh=True)
            index.require(bundle_id)
            source = next(item for item in self.sources.list() if item.id == source_id)
            return source, index
        diagnostics: list[str] = []
        for source in self.sources.list():
            try:
                index = self.sources.fetch(source.id, refresh=True)
                index.require(bundle_id)
                return source, index
            except PluginStoreError as error:
                diagnostics.append(f"{source.id}: {error}")
        details = "; ".join(diagnostics)
        raise PluginStoreError(f"plugin bundle {bundle_id!r} was not found in any source ({details})")

    @staticmethod
    def _require_runtime(runtime_kind: str) -> RuntimePlugin:
        runtime = RuntimeCatalog().discover().get(runtime_kind)
        if runtime is None:
            raise PluginStoreError(f"runtime kind {runtime_kind!r} is not installed")
        if runtime.facet_installer is None or runtime.distribution is None:
            raise PluginStoreError(f"runtime kind {runtime_kind!r} does not support managed plugin installation")
        return runtime

    def _create_environment(
        self,
        generation_path: Path,
        runtime: RuntimePlugin,
        facets: Mapping[str, PluginFacet],
    ) -> None:
        if runtime.distribution is None:
            raise AssertionError("managed runtime distribution is required")
        try:
            version = metadata.version(runtime.distribution)
        except metadata.PackageNotFoundError as error:
            raise PluginStoreError(f"runtime distribution {runtime.distribution!r} is not installed") from error
        python = self.generations.python_path(generation_path)
        self._run(["uv", "venv", "--python", sys.executable, str(generation_path / "venv")])
        self._run(["uv", "pip", "install", "--python", str(python), f"{runtime.distribution}=={version}"])
        wheels = tuple(wheel for facet in facets.values() for wheel in facet.wheels)
        if wheels:
            wheel_directory = generation_path / "wheels"
            wheel_directory.mkdir()
            wheel_paths: list[str] = []
            for wheel in wheels:
                staged = wheel_directory / f"{wheel.sha256}.whl"
                shutil.copyfile(self.artifacts.path_for(wheel.sha256), staged)
                wheel_paths.append(str(staged))
            self._run(["uv", "pip", "install", "--no-index", "--no-deps", "--python", str(python), *wheel_paths])


def _resolve_bundles(index: PluginIndex, bundle_id: str) -> tuple[PluginBundle, ...]:
    resolved: list[PluginBundle] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(current_id: str) -> None:
        if current_id in visited:
            return
        if current_id in visiting:
            raise PluginStoreError(f"plugin dependency cycle includes {current_id!r}")
        visiting.add(current_id)
        bundle = index.require(current_id)
        for dependency in bundle.dependencies:
            visit(dependency)
        visiting.remove(current_id)
        visited.add(current_id)
        resolved.append(bundle)

    visit(bundle_id)
    return tuple(resolved)


def _run_command(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise PluginStoreError(f"plugin generation command failed: {error}") from error


def _prune_empty_generation_parents(generation_path: Path) -> None:
    for directory in (generation_path.parent, generation_path.parent.parent):
        try:
            directory.rmdir()
        except OSError:
            return


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


__all__ = ["PluginInstallResult", "PluginInstallationService"]
