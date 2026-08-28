"""Canonical workspace and Alpha release policy registry."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

VersionPolicy = Literal["lockstep", "independent"]
ExpectedVersion = Literal["none", "component", "lockstep"]


class ReleaseRegistryError(RuntimeError):
    """Raised when workspace metadata and the release policy disagree."""


@dataclass(frozen=True, slots=True)
class ReleasePolicy:
    """Policy for one workspace distribution.

    The project path is the key in ``POLICIES``. Distribution name and version
    are always read from that project's metadata.
    """

    component_id: str
    version_policy: VersionPolicy
    release_name: str | None = None
    tag_prefix: str | None = None
    tag_selector: str | None = None
    verifier: str | None = None
    verifier_components: tuple[str, ...] = ()
    verifier_arguments: tuple[str, ...] = ()
    expected_version: ExpectedVersion = "none"
    requires_sdist: bool = True
    reserved: bool = False
    included_in_alpha_bundle: bool = True


@dataclass(frozen=True, slots=True)
class WorkspaceComponent:
    """Resolved metadata and policy for one workspace distribution."""

    policy: ReleasePolicy
    project_dir: str
    distribution: str
    version: str
    license: str

    @property
    def component_id(self) -> str:
        return self.policy.component_id

    @property
    def requires_sdist(self) -> bool:
        return self.policy.requires_sdist

    @property
    def reserved(self) -> bool:
        return self.policy.reserved

    @property
    def independent(self) -> bool:
        return self.policy.version_policy == "independent"

    @property
    def release_version(self) -> str:
        return self.version


@dataclass(frozen=True, slots=True)
class WorkspaceRegistry:
    """Resolved release graph for one checkout."""

    root: Path
    components: tuple[WorkspaceComponent, ...]

    @property
    def by_component_id(self) -> Mapping[str, WorkspaceComponent]:
        return {component.component_id: component for component in self.components}

    @property
    def by_distribution(self) -> Mapping[str, WorkspaceComponent]:
        return {_normalize_name(component.distribution): component for component in self.components}

    @property
    def lockstep_components(self) -> tuple[WorkspaceComponent, ...]:
        return tuple(component for component in self.components if not component.independent)

    @property
    def independent_components(self) -> tuple[WorkspaceComponent, ...]:
        return tuple(component for component in self.components if component.independent)

    @property
    def publishable_components(self) -> tuple[WorkspaceComponent, ...]:
        return tuple(
            component
            for component in self.components
            if component.policy.tag_prefix is not None and component.policy.tag_selector is not None
        )

    @property
    def verification_components(self) -> tuple[WorkspaceComponent, ...]:
        return tuple(component for component in self.components if component.policy.verifier is not None)

    @property
    def alpha_bundle_components(self) -> tuple[WorkspaceComponent, ...]:
        """Return components included in the signed CLI-first Alpha bundle."""

        return tuple(component for component in self.components if component.policy.included_in_alpha_bundle)

    @property
    def alpha_bundle_verification_components(self) -> tuple[WorkspaceComponent, ...]:
        """Return isolated verifiers required by the signed Alpha bundle."""

        return tuple(component for component in self.alpha_bundle_components if component.policy.verifier is not None)

# The tuple order is the canonical manifest and verification order.
POLICIES: tuple[tuple[str, ReleasePolicy], ...] = (
    (
        "packages/kernel",
        ReleasePolicy(
            "kernel",
            "lockstep",
            tag_prefix="kernel-v",
            tag_selector="kernel-v",
            verifier="scripts/verify_kernel_install.py",
            verifier_components=("kernel",),
            expected_version="lockstep",
        ),
    ),
    (
        ".",
        ReleasePolicy(
            "root",
            "lockstep",
            release_name="root",
            tag_prefix="v",
            tag_selector="v7.",
            verifier="scripts/verify_published_install.py",
            verifier_components=("kernel", "cordis", "adapter-onebot", "root"),
            verifier_arguments=(
                "--expect-kernel",
                "--expect-cordis",
                "--expect-adapter-onebot",
                "--expect-no-legacy-runtime",
            ),
            expected_version="lockstep",
        ),
    ),
    (
        "packages/cordis",
        ReleasePolicy(
            "cordis",
            "lockstep",
            tag_prefix="cordis-v",
            tag_selector="cordis-v",
            verifier="scripts/verify_cordis_install.py",
            verifier_components=("kernel", "cordis"),
            expected_version="lockstep",
        ),
    ),
    (
        "packages/adapter-onebot",
        ReleasePolicy(
            "adapter-onebot",
            "lockstep",
            tag_prefix="adapter-onebot-v",
            tag_selector="adapter-onebot-v",
            verifier="scripts/verify_onebot_adapter_install.py",
            verifier_components=("kernel", "adapter-onebot"),
            expected_version="lockstep",
        ),
    ),
)

POLICY_BY_PATH: Mapping[str, ReleasePolicy] = dict(POLICIES)
_NAME_PATTERN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_EXACT_REQUIREMENT = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?\s*==\s*([^\s,;]+)\s*$"
)


def _normalize_path(path: Path | str) -> str:
    value = Path(path).as_posix()
    if value in {"", "."}:
        return "."
    return value.removesuffix("/")


def _normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def normalize_distribution_name(value: str) -> str:
    """Normalize a distribution name using PEP 503 comparison rules."""

    return _normalize_name(value)


def _project(document: Mapping[str, object], *, context: str) -> dict[str, object]:
    value = document.get("project")
    if not isinstance(value, dict):
        raise ReleaseRegistryError(f"{context} does not contain a [project] table")
    return cast(dict[str, object], value)


def _read_project(project_file: Path) -> dict[str, object]:
    try:
        document = tomllib.loads(project_file.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ReleaseRegistryError(f"cannot read {project_file}") from error
    return _project(document, context=str(project_file))


def _required_string(project: Mapping[str, object], name: str, *, context: str) -> str:
    value = project.get(name)
    if not isinstance(value, str) or not value:
        raise ReleaseRegistryError(f"{context} has no non-empty project.{name}")
    return value


def _workspace_paths(root: Path) -> tuple[str, ...]:
    root_project_file = root / "pyproject.toml"
    document = tomllib.loads(root_project_file.read_text(encoding="utf-8"))
    workspace_value = document.get("tool", {})
    if not isinstance(workspace_value, dict):
        raise ReleaseRegistryError("root pyproject has an invalid tool table")
    uv_value = workspace_value.get("uv", {})
    if not isinstance(uv_value, dict):
        raise ReleaseRegistryError("root pyproject has an invalid tool.uv table")
    members = uv_value.get("workspace", {})
    if not isinstance(members, dict):
        raise ReleaseRegistryError("root pyproject has an invalid tool.uv.workspace table")
    member_patterns = members.get("members", ())
    exclude_patterns = members.get("exclude", ())
    if not isinstance(member_patterns, list) or not all(isinstance(item, str) for item in member_patterns):
        raise ReleaseRegistryError("workspace members must be a list of strings")
    if not isinstance(exclude_patterns, list) or not all(isinstance(item, str) for item in exclude_patterns):
        raise ReleaseRegistryError("workspace excludes must be a list of strings")

    excluded: set[str] = set()
    for pattern in exclude_patterns:
        excluded.update(
            _normalize_path(candidate.relative_to(root))
            for candidate in root.glob(pattern)
            if candidate.is_dir() and (candidate / "pyproject.toml").is_file()
        )

    paths = ["."]
    for pattern in member_patterns:
        for candidate in sorted(root.glob(pattern)):
            if not candidate.is_dir() or not (candidate / "pyproject.toml").is_file():
                continue
            relative = _normalize_path(candidate.relative_to(root))
            if relative not in excluded:
                paths.append(relative)
    if len(paths) != len(set(paths)):
        raise ReleaseRegistryError("workspace contains duplicate project paths")
    return tuple(paths)


def _dependency_specs(project: Mapping[str, object], *, context: str) -> tuple[str, ...]:
    specs: list[str] = []
    dependencies = project.get("dependencies", [])
    if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
        raise ReleaseRegistryError(f"{context} project.dependencies must be a list of strings")
    specs.extend(cast(list[str], dependencies))
    optional = project.get("optional-dependencies", {})
    if not isinstance(optional, dict):
        raise ReleaseRegistryError(f"{context} project.optional-dependencies must be a table")
    for group, values in optional.items():
        if (
            not isinstance(group, str)
            or not isinstance(values, list)
            or not all(isinstance(item, str) for item in values)
        ):
            raise ReleaseRegistryError(f"{context} optional dependency group is invalid")
        specs.extend(cast(list[str], values))
    return tuple(specs)


def resolve_workspace_registry(root: Path) -> WorkspaceRegistry:
    """Resolve the policy against the workspace declared by ``root``."""

    root = root.resolve()
    paths = _workspace_paths(root)
    policy_paths = set(POLICY_BY_PATH)
    actual_paths = set(paths)
    if actual_paths != policy_paths:
        missing = sorted(actual_paths - policy_paths)
        stale = sorted(policy_paths - actual_paths)
        raise ReleaseRegistryError(f"workspace/release policy mismatch: missing={missing}, stale={stale}")

    documents: dict[str, dict[str, object]] = {}
    for project_dir in paths:
        project_file = root / project_dir / "pyproject.toml"
        documents[project_dir] = _read_project(project_file)
    root_project = documents["."]
    root_version = _required_string(root_project, "version", context="pyproject.toml")
    components: list[WorkspaceComponent] = []
    for project_dir, policy in POLICIES:
        project = documents[project_dir]
        context = str(Path(project_dir) / "pyproject.toml")
        distribution = _required_string(project, "name", context=context)
        metadata_version = _required_string(project, "version", context=context)
        if policy.version_policy == "lockstep" and metadata_version != root_version:
            raise ReleaseRegistryError(
                f"{context} lockstep version {metadata_version} does not match root version {root_version}"
            )
        version = root_version if policy.version_policy == "lockstep" else metadata_version
        components.append(
            WorkspaceComponent(
                policy=policy,
                project_dir=project_dir,
                distribution=distribution,
                version=version,
                license=_required_string(project, "license", context=context),
            )
        )

    ids = [component.component_id for component in components]
    distributions = [_normalize_name(component.distribution) for component in components]
    if len(ids) != len(set(ids)) or len(distributions) != len(set(distributions)):
        raise ReleaseRegistryError("release policy contains duplicate component IDs or distributions")
    by_id = {component.component_id: component for component in components}
    included_ids = {
        component.component_id for component in components if component.policy.included_in_alpha_bundle
    }
    release_names: list[str] = []
    for component in components:
        policy = component.policy
        if (policy.tag_prefix is None) != (policy.tag_selector is None):
            raise ReleaseRegistryError(f"{component.component_id} must define both tag fields or neither")
        if policy.tag_prefix is None and policy.release_name is not None:
            raise ReleaseRegistryError(f"{component.component_id} has a release name but no tag policy")
        if policy.tag_prefix is not None:
            release_names.append(policy.release_name or component.component_id)
        for dependency in policy.verifier_components:
            if dependency not in by_id:
                raise ReleaseRegistryError(f"{component.component_id} references unknown component {dependency}")
            if policy.included_in_alpha_bundle and dependency not in included_ids:
                raise ReleaseRegistryError(
                    f"Alpha bundle component {component.component_id} references excluded component {dependency}"
                )
        if policy.verifier is None and policy.verifier_components:
            raise ReleaseRegistryError(f"{component.component_id} has verifier components without a verifier")
    if len(release_names) != len(set(release_names)):
        raise ReleaseRegistryError("release policy contains duplicate release names")
    return WorkspaceRegistry(root=root, components=tuple(components))


def validate_first_party_pins(registry: WorkspaceRegistry) -> None:
    """Require every first-party dependency to use an exact resolved version."""

    expected = registry.by_distribution
    for component in registry.components:
        project_file = registry.root / component.project_dir / "pyproject.toml"
        project = _read_project(project_file)
        context = str(Path(component.project_dir) / "pyproject.toml")
        for specification in _dependency_specs(project, context=context):
            match = _NAME_PATTERN.match(specification)
            if match is None:
                raise ReleaseRegistryError(f"{context} has an invalid dependency: {specification!r}")
            dependency = expected.get(_normalize_name(match.group(1)))
            if dependency is None:
                continue
            exact = _EXACT_REQUIREMENT.fullmatch(specification.split(";", 1)[0].strip())
            if exact is None or exact.group(2) != dependency.release_version:
                raise ReleaseRegistryError(
                    f"{context} must pin {dependency.distribution}=={dependency.release_version}; "
                    f"found {specification!r}"
                )


__all__ = [
    "POLICIES",
    "POLICY_BY_PATH",
    "ReleasePolicy",
    "ReleaseRegistryError",
    "WorkspaceComponent",
    "WorkspaceRegistry",
    "normalize_distribution_name",
    "resolve_workspace_registry",
    "validate_first_party_pins",
]
