"""Validate source release identities before building or publishing."""

from __future__ import annotations

import argparse
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


RELEASE_PROJECTS: dict[str, ReleaseProject] = {
    "root": ReleaseProject(
        name="root",
        project_dir=".",
        distribution="liteyukibot-v7",
        tag_prefix="v",
        tag_selector="v7.",
        verifier="scripts/verify_published_install.py",
    ),
    "permissions": ReleaseProject(
        name="permissions",
        project_dir="packages/permissions",
        distribution="liteyukibot-v7-permissions",
        tag_prefix="permissions-v",
        tag_selector="permissions-v",
        verifier="scripts/verify_permissions_install.py",
    ),
    "commands": ReleaseProject(
        name="commands",
        project_dir="packages/commands",
        distribution="liteyukibot-v7-commands",
        tag_prefix="commands-v",
        tag_selector="commands-v",
        verifier="scripts/verify_commands_install.py",
    ),
    "essentials": ReleaseProject(
        name="essentials",
        project_dir="packages/essentials",
        distribution="liteyukibot-v7-essentials",
        tag_prefix="essentials-v",
        tag_selector="essentials-v",
        verifier="scripts/verify_essentials_install.py",
    ),
}


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
) -> None:
    if identity.distribution != project.distribution:
        raise RuntimeError(
            f"expected project.name={project.distribution!r}, got {identity.distribution!r}"
        )
    if tag is not None:
        expected_tag = f"{project.tag_prefix}{identity.version}"
        if tag != expected_tag:
            raise RuntimeError(f"expected release tag {expected_tag!r}, got {tag!r}")


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
    args = parser.parse_args()

    if args.package is not None:
        project = RELEASE_PROJECTS[args.package]
    elif args.tag is not None:
        project = project_for_tag(args.tag)
    else:
        project = RELEASE_PROJECTS["root"]
    identity = read_release_identity(project.project_file)
    validate_release(identity, project=project, tag=args.tag)
    result = _result(project, identity)

    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as output:
            for name, value in result.items():
                output.write(f"{name}={value}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
