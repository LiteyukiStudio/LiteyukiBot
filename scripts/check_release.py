"""Validate source release identities before building or publishing."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

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
    "resources": ReleaseProject(
        name="resources",
        project_dir="packages/resources",
        distribution="liteyukibot-v7-resources",
        tag_prefix="resources-v",
        tag_selector="resources-v",
        verifier="scripts/verify_resources_install.py",
    ),
    "functions": ReleaseProject(
        name="functions",
        project_dir="packages/functions",
        distribution="liteyukibot-v7-functions",
        tag_prefix="functions-v",
        tag_selector="functions-v",
        verifier="scripts/verify_functions_install.py",
    ),
    "profile": ReleaseProject(
        name="profile",
        project_dir="packages/profile",
        distribution="liteyukibot-v7-profile",
        tag_prefix="profile-v",
        tag_selector="profile-v",
        verifier="scripts/verify_profile_install.py",
    ),
    "essentials": ReleaseProject(
        name="essentials",
        project_dir="packages/essentials",
        distribution="liteyukibot-v7-essentials",
        tag_prefix="essentials-v",
        tag_selector="essentials-v",
        verifier="scripts/verify_essentials_install.py",
    ),
    "runtime-nonebot": ReleaseProject(
        name="runtime-nonebot",
        project_dir="packages/runtime-nonebot",
        distribution="liteyukibot-v7-runtime-nonebot",
        tag_prefix="runtime-nonebot-v",
        tag_selector="runtime-nonebot-v",
        verifier="scripts/verify_nonebot_runtime_install.py",
    ),
    "runtime-adapter": ReleaseProject(
        name="runtime-adapter",
        project_dir="packages/runtime-adapter",
        distribution="liteyukibot-v7-runtime-adapter",
        tag_prefix="runtime-adapter-v",
        tag_selector="runtime-adapter-v",
        verifier="scripts/verify_adapter_runtime_install.py",
    ),
    "adapter-onebot": ReleaseProject(
        name="adapter-onebot",
        project_dir="packages/adapter-onebot",
        distribution="liteyukibot-v7-adapter-onebot",
        tag_prefix="adapter-onebot-v",
        tag_selector="adapter-onebot-v",
        verifier="scripts/verify_onebot_adapter_install.py",
    ),
    "adapter-satori": ReleaseProject(
        name="adapter-satori",
        project_dir="packages/adapter-satori",
        distribution="liteyukibot-v7-adapter-satori",
        tag_prefix="adapter-satori-v",
        tag_selector="adapter-satori-v",
        verifier="scripts/verify_satori_adapter_install.py",
    ),
    "agent-resolver": ReleaseProject(
        name="agent-resolver",
        project_dir="packages/agent-resolver",
        distribution="liteyukibot-v7-agent-resolver",
        tag_prefix="agent-resolver-v",
        tag_selector="agent-resolver-v",
        verifier="scripts/verify_agent_resolver_install.py",
    ),
    "agent": ReleaseProject(
        name="agent",
        project_dir="packages/agent",
        distribution="liteyukibot-v7-agent",
        tag_prefix="agent-v",
        tag_selector="agent-v",
        verifier="scripts/verify_agent_install.py",
    ),
    "webui": ReleaseProject(
        name="webui",
        project_dir="packages/webui",
        distribution="liteyukibot-v7-webui",
        tag_prefix="webui-v",
        tag_selector="webui-v",
        verifier="scripts/verify_webui_install.py",
    ),
    "ipc-native": ReleaseProject(
        name="ipc-native",
        project_dir="packages/ipc-native",
        distribution="liteyukibot-v7-ipc-native",
        tag_prefix="ipc-native-v",
        tag_selector="ipc-native-v",
        verifier="scripts/verify_ipc_native_install.py",
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
