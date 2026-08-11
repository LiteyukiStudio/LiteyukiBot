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


@dataclass(frozen=True, slots=True)
class PluginUninstallResult:
    """The deployment state produced by removing one requested bundle root."""

    source_id: str
    generation: RuntimeGeneration | None


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
        current = self._active_generation(runtime_id, runtime_kind)
        roots: tuple[str, ...]
        if current is None:
            source, index = self._resolve_source(bundle_id, source_id)
            roots = (bundle_id,)
        else:
            self._require_resolution(current)
            if bundle_id in current.roots:
                raise PluginStoreError(f"plugin bundle {bundle_id!r} is already an enabled root")
            source, index = self._refresh_source(current, source_id)
            roots = (*current.roots, bundle_id)
        return self._build(runtime_id, runtime_kind, source.id, index, roots)

    def update(
        self,
        *,
        runtime_id: str,
        runtime_kind: str,
        source_id: str | None = None,
    ) -> PluginInstallResult:
        current = self._require_active_generation(runtime_id, runtime_kind)
        self._require_resolution(current)
        source, index = self._refresh_source(current, source_id)
        return self._build(runtime_id, runtime_kind, source.id, index, current.roots)

    def uninstall(
        self,
        bundle_id: str,
        *,
        runtime_id: str,
        runtime_kind: str,
    ) -> PluginUninstallResult:
        current = self._require_active_generation(runtime_id, runtime_kind)
        self._require_resolution(current)
        if bundle_id not in current.roots:
            raise PluginStoreError(f"plugin bundle {bundle_id!r} is not an enabled root")
        roots = tuple(item for item in current.roots if item != bundle_id)
        if not roots:
            self.generations.deactivate(runtime_id)
            return PluginUninstallResult(current.source_id or "", None)
        index = PluginIndex(current.resolved_bundles)
        result = self._build(runtime_id, runtime_kind, current.source_id or "", index, roots, current.index_digest)
        return PluginUninstallResult(result.source_id, result.generation)

    def _build(
        self,
        runtime_id: str,
        runtime_kind: str,
        source_id: str,
        index: PluginIndex,
        roots: tuple[str, ...],
        index_digest: str | None = None,
    ) -> PluginInstallResult:
        bundles = _resolve_bundles(index, roots)
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
                source_id=source_id,
                index_digest=index_digest or index.digest,
                roots=roots,
                resolved_bundles=bundles,
            )
            self.generations.write(generation)
            self.generations.activate(runtime_id, generation_id)
        except BaseException:
            shutil.rmtree(generation_path, ignore_errors=True)
            _prune_empty_generation_parents(generation_path)
            raise
        return PluginInstallResult(source_id, generation)

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

    def _refresh_source(self, generation: RuntimeGeneration, source_id: str | None) -> tuple[PluginSource, PluginIndex]:
        if source_id is not None and source_id != generation.source_id:
            raise PluginStoreError("an active runtime generation cannot combine plugin sources")
        if generation.source_id is None:
            raise PluginStoreError("active runtime generation has no source provenance; reinstall its plugin roots")
        index = self.sources.fetch(generation.source_id, refresh=True)
        source = next(item for item in self.sources.list() if item.id == generation.source_id)
        return source, index

    def _active_generation(self, runtime_id: str, runtime_kind: str) -> RuntimeGeneration | None:
        deployment = self.generations.active()
        generation_id = deployment.runtime_generations.get(runtime_id)
        if generation_id is None:
            return None
        generation = self.generations.read(runtime_id, generation_id)
        if generation.runtime_kind != runtime_kind:
            raise PluginStoreError(
                f"runtime {runtime_id!r} has {generation.runtime_kind!r} plugins, not {runtime_kind!r} plugins"
            )
        return generation

    def _require_active_generation(self, runtime_id: str, runtime_kind: str) -> RuntimeGeneration:
        generation = self._active_generation(runtime_id, runtime_kind)
        if generation is None:
            raise PluginStoreError(f"runtime {runtime_id!r} has no active plugin generation")
        return generation

    @staticmethod
    def _require_resolution(generation: RuntimeGeneration) -> None:
        if generation.source_id is None:
            raise PluginStoreError("active runtime generation has no source provenance; reinstall its plugin roots")

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


def _resolve_bundles(index: PluginIndex, roots: tuple[str, ...]) -> tuple[PluginBundle, ...]:
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

    for root in roots:
        visit(root)
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


__all__ = ["PluginInstallResult", "PluginInstallationService", "PluginUninstallResult"]
