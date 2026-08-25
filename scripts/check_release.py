"""Validate source release identities before building or publishing."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

try:
    from scripts.release_registry import ReleaseRegistryError, resolve_workspace_registry
except ModuleNotFoundError:  # pragma: no cover - exercised by direct script execution
    from release_registry import (  # type: ignore[import-not-found, no-redef]
        ReleaseRegistryError,
        resolve_workspace_registry,
    )

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ALPHA_VERSION = re.compile(r"a\d+(?:[.+-]|$)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ReleaseIdentity:
    distribution: str
    version: str


@dataclass(frozen=True, slots=True)
class ReleaseProject:
    name: str
    project_dir: str
    distribution: str
    tag_prefix: str
    tag_selector: str
    verifier: str

    @property
    def project_file(self) -> Path:
        return PROJECT_ROOT / self.project_dir / "pyproject.toml"


def _release_projects() -> dict[str, ReleaseProject]:
    try:
        registry = resolve_workspace_registry(PROJECT_ROOT)
    except ReleaseRegistryError as error:
        raise RuntimeError(str(error)) from error
    projects: dict[str, ReleaseProject] = {}
    for component in registry.publishable_components:
        policy = component.policy
        if policy.tag_prefix is None or policy.tag_selector is None or policy.verifier is None:
            raise RuntimeError(f"publishable component {component.component_id} has incomplete release policy")
        project_name = policy.release_name or component.component_id
        projects[project_name] = ReleaseProject(
            name=project_name,
            project_dir=component.project_dir,
            distribution=component.distribution,
            tag_prefix=policy.tag_prefix,
            tag_selector=policy.tag_selector,
            verifier=policy.verifier,
        )
    return projects


RELEASE_PROJECTS: dict[str, ReleaseProject] = _release_projects()


def read_release_identity(project_file: Path) -> ReleaseIdentity:
    document = tomllib.loads(project_file.read_text(encoding="utf-8"))
    project_value: object = document.get("project")
    if not isinstance(project_value, dict):
        raise RuntimeError(f"{project_file} does not contain a [project] table")
    project = cast(dict[str, object], project_value)
    distribution = project.get("name")
    version = project.get("version")
    if not isinstance(distribution, str) or not distribution:
        raise RuntimeError("project.name must be a non-empty string")
    if not isinstance(version, str) or not version:
        raise RuntimeError("project.version must be a non-empty string")
    return ReleaseIdentity(distribution=distribution, version=version)


def project_for_tag(tag: str) -> ReleaseProject:
    matches = tuple(project for project in RELEASE_PROJECTS.values() if tag.startswith(project.tag_selector))
    if len(matches) != 1:
        raise RuntimeError(f"release tag {tag!r} does not select exactly one project")
    return matches[0]


def validate_release(
    identity: ReleaseIdentity,
    *,
    project: ReleaseProject = RELEASE_PROJECTS["root"],
    tag: str | None = None,
    reject_alpha: bool = False,
) -> None:
    if identity.distribution != project.distribution:
        raise RuntimeError(f"expected project.name={project.distribution!r}, got {identity.distribution!r}")
    if tag is not None:
        expected_tag = f"{project.tag_prefix}{identity.version}"
        if tag != expected_tag:
            raise RuntimeError(f"expected release tag {expected_tag!r}, got {tag!r}")
    if reject_alpha and _ALPHA_VERSION.search(identity.version):
        raise RuntimeError("Alpha releases must use the signed GitHub bundle workflow, not PyPI")


def _result(project: ReleaseProject, identity: ReleaseIdentity) -> dict[str, str]:
    return {
        "package": project.name,
        "project": project.project_dir,
        "distribution": identity.distribution,
        "version": identity.version,
        "verifier": project.verifier,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", choices=tuple(RELEASE_PROJECTS))
    parser.add_argument("--tag")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--reject-alpha", action="store_true")
    args = parser.parse_args()

    if args.package is not None:
        project = RELEASE_PROJECTS[args.package]
    elif args.tag is not None:
        project = project_for_tag(args.tag)
    else:
        project = RELEASE_PROJECTS["root"]
    identity = read_release_identity(project.project_file)
    validate_release(identity, project=project, tag=args.tag, reject_alpha=args.reject_alpha)
    result = _result(project, identity)

    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as output:
            for name, value in result.items():
                output.write(f"{name}={value}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
