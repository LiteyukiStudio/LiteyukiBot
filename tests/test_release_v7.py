from __future__ import annotations

import importlib.metadata
from pathlib import Path

import pytest
from scripts.check_release import (
    RELEASE_PROJECTS,
    ReleaseIdentity,
    project_for_tag,
    read_release_identity,
    validate_release,
)
from scripts.run_isolated_install import _clean_environment, _requirement

import liteyukibot


def test_kernel_import_namespace_uses_distribution_version() -> None:
    expected = importlib.metadata.version("liteyukibot-v7")

    assert liteyukibot.__version__ == expected


@pytest.mark.parametrize(
    ("name", "tag"),
    [
        ("root", "v7.0.0a11"),
        ("permissions", "permissions-v0.2.0a1"),
        ("commands", "commands-v0.2.0a2"),
        ("resources", "resources-v0.1.0a2"),
        ("functions", "functions-v0.1.0a2"),
        ("profile", "profile-v0.1.0a2"),
        ("essentials", "essentials-v0.2.0a3"),
        ("runtime-nonebot", "runtime-nonebot-v0.1.0a1"),
        ("runtime-adapter", "runtime-adapter-v0.1.0a2"),
        ("adapter-onebot", "adapter-onebot-v0.1.0a1"),
        ("runtime-v6", "runtime-v6-v0.1.0a2"),
        ("agent-resolver", "agent-resolver-v0.1.0a1"),
        ("agent", "agent-v0.1.0a3"),
        ("runtime-astrbot", "runtime-astrbot-v0.1.0a3"),
        ("runtime-mofox", "runtime-mofox-v0.1.0a3"),
    ],
)
def test_current_release_identities_accept_exact_tags(name: str, tag: str) -> None:
    project = RELEASE_PROJECTS[name]
    identity = read_release_identity(project.project_file)

    validate_release(identity, project=project, tag=tag)
    assert identity.distribution == project.distribution
    assert project_for_tag(tag) == project


@pytest.mark.parametrize(
    ("identity", "project_name", "tag", "message"),
    [
        (ReleaseIdentity("liteyukibot", "7.0.0a5"), "root", None, "project.name"),
        (ReleaseIdentity("liteyukibot-v7", "7.0.0a5"), "root", "v7.0.0a2", "release tag"),
        (
            ReleaseIdentity("liteyukibot-v7-commands", "0.2.0a1"),
            "commands",
            "permissions-v0.2.0a1",
            "release tag",
        ),
    ],
)
def test_release_identity_rejects_mismatches(
    identity: ReleaseIdentity,
    project_name: str,
    tag: str | None,
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        validate_release(identity, project=RELEASE_PROJECTS[project_name], tag=tag)


@pytest.mark.parametrize("tag", ["v6.9.0", "plugin-v0.1.0", ""])
def test_release_tag_must_select_a_known_project(tag: str) -> None:
    with pytest.raises(RuntimeError, match="does not select"):
        project_for_tag(tag)


def test_isolated_install_environment_removes_workspace_inheritance() -> None:
    cleaned = _clean_environment(
        {
            "PATH": "bin",
            "VIRTUAL_ENV": "workspace/.venv",
            "PYTHONPATH": "workspace/src",
            "UV_PROJECT_ENVIRONMENT": "workspace/.venv",
            "UV_WORKING_DIRECTORY": "workspace",
        }
    )

    assert cleaned == {"PATH": "bin"}


def test_isolated_install_rejects_empty_and_directory_requirements(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        _requirement("")
    with pytest.raises(ValueError, match="must be a file"):
        _requirement(str(tmp_path))
