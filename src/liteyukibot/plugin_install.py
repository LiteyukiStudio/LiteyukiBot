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
        """Initialize the plugin installation service.

        Args:
            workspace: The workspace value used by the operation.
            run: The run value used by the operation.

        Returns:
            None.
        """
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
        """Install the plugin installation service operation.

        Args:
            bundle_id: Stable identifier for the bundle.
            runtime_id: Stable runtime identifier.
            runtime_kind: The runtime kind value used by the operation.
            source_id: Stable identifier for the source.

        Returns:
            The `PluginInstallResult` result produced by the operation.
        """
        current = self._active_generation(runtime_id, runtime_kind)
        roots: tuple[str, ...]
        disabled_roots: tuple[str, ...]
        if current is None:
            source, index = self._resolve_source(bundle_id, source_id)
            roots = (bundle_id,)
            disabled_roots = ()
        else:
            self._require_resolution(current)
            if bundle_id in current.roots:
                if bundle_id in current.disabled_roots:
                    raise PluginStoreError(f"plugin bundle {bundle_id!r} is disabled; use plugin enable")
                raise PluginStoreError(f"plugin bundle {bundle_id!r} is already an enabled root")
            source, index = self._refresh_source(current, source_id)
            roots = (*current.roots, bundle_id)
            disabled_roots = current.disabled_roots
        return self._build(runtime_id, runtime_kind, source.id, index, roots, disabled_roots)

    def update(
        self,
        *,
        runtime_id: str,
        runtime_kind: str,
        source_id: str | None = None,
    ) -> PluginInstallResult:
        """Update the plugin installation service operation.

        Args:
            runtime_id: Stable runtime identifier.
            runtime_kind: The runtime kind value used by the operation.
            source_id: Stable identifier for the source.

        Returns:
            The `PluginInstallResult` result produced by the operation.
        """
        current = self._require_active_generation(runtime_id, runtime_kind)
        self._require_resolution(current)
        source, index = self._refresh_source(current, source_id)
        return self._build(runtime_id, runtime_kind, source.id, index, current.roots, current.disabled_roots)

    def disable(
        self,
        bundle_id: str,
        *,
        runtime_id: str,
        runtime_kind: str,
    ) -> PluginInstallResult:
        """Implement the disable operation for the plugin installation service.

        Args:
            bundle_id: Stable identifier for the bundle.
            runtime_id: Stable runtime identifier.
            runtime_kind: The runtime kind value used by the operation.

        Returns:
            The `PluginInstallResult` result produced by the operation.
        """
        current = self._require_active_generation(runtime_id, runtime_kind)
        self._require_resolution(current)
        if bundle_id not in current.roots:
            raise PluginStoreError(f"plugin bundle {bundle_id!r} is not an enabled root")
        if bundle_id in current.disabled_roots:
            raise PluginStoreError(f"plugin bundle {bundle_id!r} is already disabled")
        index = PluginIndex(current.resolved_bundles)
        enabled_roots = tuple(
            root for root in current.roots if root != bundle_id and root not in current.disabled_roots
        )
        dependents = _roots_requiring(index, enabled_roots, bundle_id)
        if dependents:
            raise PluginStoreError(
                f"plugin bundle {bundle_id!r} is required by enabled roots: {', '.join(dependents)}"
            )
        return self._build(
            runtime_id,
            runtime_kind,
            current.source_id or "",
            index,
            current.roots,
            (*current.disabled_roots, bundle_id),
            current.index_digest,
            fetch_missing=False,
        )

    def enable(
        self,
        bundle_id: str,
        *,
        runtime_id: str,
        runtime_kind: str,
    ) -> PluginInstallResult:
        """Implement the enable operation for the plugin installation service.

        Args:
            bundle_id: Stable identifier for the bundle.
            runtime_id: Stable runtime identifier.
            runtime_kind: The runtime kind value used by the operation.

        Returns:
            The `PluginInstallResult` result produced by the operation.
        """
        current = self._require_active_generation(runtime_id, runtime_kind)
        self._require_resolution(current)
        if bundle_id not in current.disabled_roots:
            raise PluginStoreError(f"plugin bundle {bundle_id!r} is not disabled")
        return self._build(
            runtime_id,
            runtime_kind,
            current.source_id or "",
            PluginIndex(current.resolved_bundles),
            current.roots,
            tuple(root for root in current.disabled_roots if root != bundle_id),
            current.index_digest,
            fetch_missing=False,
        )

    def uninstall(
        self,
        bundle_id: str,
        *,
        runtime_id: str,
        runtime_kind: str,
    ) -> PluginUninstallResult:
        """Implement the uninstall operation for the plugin installation service.

        Args:
            bundle_id: Stable identifier for the bundle.
            runtime_id: Stable runtime identifier.
            runtime_kind: The runtime kind value used by the operation.

        Returns:
            The `PluginUninstallResult` result produced by the operation.
        """
        current = self._require_active_generation(runtime_id, runtime_kind)
        self._require_resolution(current)
        if bundle_id not in current.roots:
            raise PluginStoreError(f"plugin bundle {bundle_id!r} is not an enabled root")
        roots = tuple(item for item in current.roots if item != bundle_id)
        index = PluginIndex(current.resolved_bundles)
        dependents = _roots_requiring(index, roots, bundle_id)
        if dependents:
            raise PluginStoreError(f"plugin bundle {bundle_id!r} is required by roots: {', '.join(dependents)}")
        if not roots:
            self.generations.deactivate(runtime_id)
            return PluginUninstallResult(current.source_id or "", None)
        disabled_roots = tuple(root for root in current.disabled_roots if root != bundle_id)
        result = self._build(
            runtime_id,
            runtime_kind,
            current.source_id or "",
            index,
            roots,
            disabled_roots,
            current.index_digest,
            fetch_missing=False,
        )
        return PluginUninstallResult(result.source_id, result.generation)

    def _build(
        self,
        runtime_id: str,
        runtime_kind: str,
        source_id: str,
        index: PluginIndex,
        roots: tuple[str, ...],
        disabled_roots: tuple[str, ...],
        index_digest: str | None = None,
        *,
        fetch_missing: bool = True,
    ) -> PluginInstallResult:
        """Build the plugin installation service operation.

        Args:
            runtime_id: Stable runtime identifier.
            runtime_kind: The runtime kind value used by the operation.
            source_id: Stable identifier for the source.
            index: The index value used by the operation.
            roots: The roots value used by the operation.
            disabled_roots: The disabled roots value used by the operation.
            index_digest: The index digest value used by the operation.
            fetch_missing: The fetch missing value used by the operation.

        Returns:
            The `PluginInstallResult` result produced by the operation.

        Notes:
            Internal implementation detail for `PluginInstallationService._build`. It delegates to
            `_resolve_bundles`, `current`, `facet_for`, `items` while keeping intermediate state local to
            the owning operation.
        """
        bundles = _resolve_bundles(index, roots)
        target = PlatformTarget.current()
        facets = {bundle.id: bundle.facet_for(runtime_kind, target) for bundle in bundles}
        enabled_roots = tuple(root for root in roots if root not in disabled_roots)
        enabled_bundle_ids = {bundle.id for bundle in _resolve_bundles(index, enabled_roots)}
        enabled_facets = {bundle_id: facet for bundle_id, facet in facets.items() if bundle_id in enabled_bundle_ids}
        runtime = self._require_runtime(runtime_kind)
        generation_id = self.generations.new_generation_id()
        generation_path = self.generations.path_for(runtime_id, generation_id)
        try:
            generation_path.mkdir(parents=True)
            for facet in facets.values():
                for artifact in (*facet.artifacts, *facet.wheels):
                    if fetch_missing:
                        self.artifacts.fetch(artifact)
                    else:
                        self.artifacts.require(artifact.sha256)
            self._create_environment(generation_path, runtime, facets, offline=not fetch_missing)
            installer = runtime.facet_installer
            if installer is None:
                raise AssertionError("managed runtime installer is required")
            load_plan = installer.materialize(self.artifacts, generation_path, enabled_facets)
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
                disabled_roots=disabled_roots,
            )
            self.generations.write(generation)
            self.generations.read(runtime_id, generation_id)
            self._probe_generation(generation_path, runtime)
            self.generations.activate(runtime_id, generation_id)
        except BaseException:
            shutil.rmtree(generation_path, ignore_errors=True)
            _prune_empty_generation_parents(generation_path)
            raise
        return PluginInstallResult(source_id, generation)

    def _resolve_source(self, bundle_id: str, source_id: str | None) -> tuple[PluginSource, PluginIndex]:
        """Resolve source.

        Args:
            bundle_id: Stable identifier for the bundle.
            source_id: Stable identifier for the source.

        Returns:
            The `tuple[PluginSource, PluginIndex]` result produced by the operation.

        Notes:
            Internal implementation detail for `PluginInstallationService._resolve_source`. It delegates to
            `fetch`, `require`, `next`, `append` while keeping intermediate state local to the owning
            operation.
        """
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
        """Implement the refresh source operation for the plugin installation service.

        Args:
            generation: Positive protocol or deployment generation.
            source_id: Stable identifier for the source.

        Returns:
            The `tuple[PluginSource, PluginIndex]` result produced by the operation.

        Notes:
            Internal implementation detail for `PluginInstallationService._refresh_source`. It delegates to
            `fetch`, `next` while keeping intermediate state local to the owning operation.
        """
        if source_id is not None and source_id != generation.source_id:
            raise PluginStoreError("an active runtime generation cannot combine plugin sources")
        if generation.source_id is None:
            raise PluginStoreError("active runtime generation has no source provenance; reinstall its plugin roots")
        index = self.sources.fetch(generation.source_id, refresh=True)
        source = next(item for item in self.sources.list() if item.id == generation.source_id)
        return source, index

    def _active_generation(self, runtime_id: str, runtime_kind: str) -> RuntimeGeneration | None:
        """Implement the active generation operation for the plugin installation service.

        Args:
            runtime_id: Stable runtime identifier.
            runtime_kind: The runtime kind value used by the operation.

        Returns:
            The `RuntimeGeneration | None` result produced by the operation.

        Notes:
            Internal implementation detail for `PluginInstallationService._active_generation`. It delegates
            to `active`, `get`, `read` while keeping intermediate state local to the owning operation.
        """
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
        """Return active generation, failing when it is unavailable.

        Args:
            runtime_id: Stable runtime identifier.
            runtime_kind: The runtime kind value used by the operation.

        Returns:
            The `RuntimeGeneration` result produced by the operation.

        Notes:
            Internal implementation detail for `PluginInstallationService._require_active_generation`. It
            delegates to `_active_generation` while keeping intermediate state local to the owning
            operation.
        """
        generation = self._active_generation(runtime_id, runtime_kind)
        if generation is None:
            raise PluginStoreError(f"runtime {runtime_id!r} has no active plugin generation")
        return generation

    @staticmethod
    def _require_resolution(generation: RuntimeGeneration) -> None:
        """Return resolution, failing when it is unavailable.

        Args:
            generation: Positive protocol or deployment generation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `PluginInstallationService._require_resolution`. It performs
            the local state transition directly and is not a stable extension boundary.
        """
        if generation.source_id is None:
            raise PluginStoreError("active runtime generation has no source provenance; reinstall its plugin roots")

    @staticmethod
    def _require_runtime(runtime_kind: str) -> RuntimePlugin:
        """Return runtime, failing when it is unavailable.

        Args:
            runtime_kind: The runtime kind value used by the operation.

        Returns:
            The `RuntimePlugin` result produced by the operation.

        Notes:
            Internal implementation detail for `PluginInstallationService._require_runtime`. It delegates to
            `get`, `discover` while keeping intermediate state local to the owning operation.
        """
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
        *,
        offline: bool,
    ) -> None:
        """Create environment.

        Args:
            generation_path: Filesystem path for the generation.
            runtime: The runtime value used by the operation.
            facets: The facets value used by the operation.
            offline: The offline value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `PluginInstallationService._create_environment`. It delegates
            to `version`, `python_path`, `_run`, `append` while keeping intermediate state local to the
            owning operation.
        """
        if runtime.distribution is None:
            raise AssertionError("managed runtime distribution is required")
        try:
            version = metadata.version(runtime.distribution)
        except metadata.PackageNotFoundError as error:
            raise PluginStoreError(f"runtime distribution {runtime.distribution!r} is not installed") from error
        python = self.generations.python_path(generation_path)
        self._run(["uv", "venv", "--python", sys.executable, str(generation_path / "venv")])
        command = ["uv", "pip", "install"]
        if offline:
            command.append("--offline")
        command.extend(["--python", str(python), f"{runtime.distribution}=={version}"])
        self._run(command)
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

    def _probe_generation(self, generation_path: Path, runtime: RuntimePlugin) -> None:
        """Verify the isolated runtime host imports before changing deployment state.

        Args:
            generation_path: Filesystem path for the generation.
            runtime: The runtime value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `PluginInstallationService._probe_generation`. It delegates
            to `_runtime_module`, `python_path`, `_run` while keeping intermediate state local to the owning
            operation.
        """

        module = _runtime_module(runtime)
        python = self.generations.python_path(generation_path)
        self._run(
            [
                str(python),
                "-c",
                "import importlib, importlib.metadata, sys; "
                "importlib.metadata.distribution(sys.argv[1]); "
                "importlib.import_module(sys.argv[2])",
                runtime.distribution or "",
                module,
            ]
        )


def _resolve_bundles(index: PluginIndex, roots: tuple[str, ...]) -> tuple[PluginBundle, ...]:
    """Resolve bundles.

    Args:
        index: The index value used by the operation.
        roots: The roots value used by the operation.

    Returns:
        The `tuple[PluginBundle, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_resolve_bundles`. It delegates to `visit` while keeping
        intermediate state local to the owning operation.
    """
    resolved: list[PluginBundle] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(current_id: str) -> None:
        """Implement the visit operation for the resolve bundles.

        Args:
            current_id: Stable identifier for the current.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_resolve_bundles.visit`. It delegates to `add`, `require`,
            `visit`, `remove` while keeping intermediate state local to the owning operation.
        """
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


def _runtime_module(runtime: RuntimePlugin) -> str:
    """Implement the runtime module operation for the component.

    Args:
        runtime: The runtime value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_runtime_module`. It delegates to `index`, `startswith`
        while keeping intermediate state local to the owning operation.
    """
    try:
        marker = runtime.command.index("-m")
        module = runtime.command[marker + 1]
    except (ValueError, IndexError) as error:
        raise PluginStoreError(
            f"managed runtime kind {runtime.kind!r} command must contain a Python -m module"
        ) from error
    if not module or module.startswith("-"):
        raise PluginStoreError(f"managed runtime kind {runtime.kind!r} command has an invalid Python module")
    return module


def _roots_requiring(index: PluginIndex, roots: tuple[str, ...], bundle_id: str) -> tuple[str, ...]:
    """Implement the roots requiring operation for the component.

    Args:
        index: The index value used by the operation.
        roots: The roots value used by the operation.
        bundle_id: Stable identifier for the bundle.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_roots_requiring`. It delegates to `_resolve_bundles` while
        keeping intermediate state local to the owning operation.
    """
    return tuple(
        root
        for root in roots
        if bundle_id in {bundle.id for bundle in _resolve_bundles(index, (root,))}
    )


def _run_command(command: list[str]) -> None:
    """Run command.

    Args:
        command: Command or operation name to execute.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_run_command`. It delegates to `run` while keeping
        intermediate state local to the owning operation.
    """
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise PluginStoreError(f"plugin generation command failed: {error}") from error


def _prune_empty_generation_parents(generation_path: Path) -> None:
    """Implement the prune empty generation parents operation for the component.

    Args:
        generation_path: Filesystem path for the generation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_prune_empty_generation_parents`. It delegates to `rmdir`
        while keeping intermediate state local to the owning operation.
    """
    for directory in (generation_path.parent, generation_path.parent.parent):
        try:
            directory.rmdir()
        except OSError:
            return


def _utc_now() -> str:
    """Implement the utc now operation for the component.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_utc_now`. It delegates to `isoformat`, `now` while keeping
        intermediate state local to the owning operation.
    """
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


__all__ = ["PluginInstallResult", "PluginInstallationService", "PluginUninstallResult"]
