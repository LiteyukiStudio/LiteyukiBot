from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

import pytest
from scripts.bundles import BUNDLE_TAG, BUNDLE_VERSION
from scripts.check_release import (
    RELEASE_PROJECTS,
    ReleaseIdentity,
    project_for_tag,
    read_release_identity,
    validate_release,
)
from scripts.release_registry import resolve_workspace_registry, validate_first_party_pins
from scripts.run_isolated_install import _clean_environment, _requirement

ROOT = Path(__file__).resolve().parents[1]
TARGET_DISTRIBUTIONS = {
    "liteyukibot-v7",
    "liteyukibot-v7-kernel",
    "liteyukibot-v7-cordis",
    "liteyukibot-v7-adapter-onebot",
}


def test_root_version_comes_from_the_target_distribution() -> None:
    assert BUNDLE_VERSION == "7.0.0a15"
    assert importlib.metadata.version("liteyukibot-v7") == BUNDLE_VERSION


def test_release_registry_contains_exactly_the_four_alpha_distributions() -> None:
    registry = resolve_workspace_registry(ROOT)

    assert {component.distribution for component in registry.components} == TARGET_DISTRIBUTIONS
    assert {component.project_dir for component in registry.components} == {
        ".",
        "packages/kernel",
        "packages/cordis",
        "packages/adapter-onebot",
    }
    assert len(registry.components) == 4
    assert not registry.independent_components
    assert {component.component_id for component in registry.verification_components} == {
        "kernel",
        "root",
        "cordis",
        "adapter-onebot",
    }


def test_publishable_projection_contains_only_target_projects() -> None:
    assert set(RELEASE_PROJECTS) == {"kernel", "root", "cordis", "adapter-onebot"}
    for project in RELEASE_PROJECTS.values():
        identity = read_release_identity(project.project_file)
        tag = BUNDLE_TAG if project.name == "root" else f"{project.tag_prefix}{identity.version}"
        validate_release(identity, project=project, tag=tag)
        assert project_for_tag(tag) == project


def test_workspace_first_party_dependencies_are_exactly_pinned() -> None:
    validate_first_party_pins(resolve_workspace_registry(ROOT))
    root_project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "liteyukibot-v7-kernel==7.0.0a15" in root_project
    assert "liteyukibot-v7-cordis==7.0.0a15" in root_project
    assert "liteyukibot-v7-adapter-onebot==7.0.0a15" in root_project
    assert "liteyukibot-v7-broker" not in root_project


@pytest.mark.parametrize(
    ("identity", "project_name", "tag", "message"),
    [
        (ReleaseIdentity("liteyukibot", "7.0.0a5"), "root", None, "project.name"),
        (ReleaseIdentity("liteyukibot-v7", "7.0.0a5"), "root", "v7.0.0a3", "release tag"),
        (
            ReleaseIdentity("liteyukibot-v7-cordis", "7.0.0a15"),
            "cordis",
            "kernel-v7.0.0a15",
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


def test_release_identity_rejects_alpha_from_pypi_workflows() -> None:
    with pytest.raises(RuntimeError, match="signed GitHub bundle"):
        validate_release(
            ReleaseIdentity("liteyukibot-v7", "7.0.0a15"),
            project=RELEASE_PROJECTS["root"],
            tag="v7.0.0a15",
            reject_alpha=True,
        )


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


def test_isolated_install_resolves_exactly_one_local_requirement_pattern(tmp_path: Path) -> None:
    wheel = tmp_path / f"liteyukibot_v7-{BUNDLE_VERSION}-py3-none-any.whl"
    wheel.touch()

    assert _requirement(str(tmp_path / "liteyukibot_v7-*.whl")) == str(wheel.resolve())

    (tmp_path / f"liteyukibot_v7-{BUNDLE_VERSION}.post1-py3-none-any.whl").touch()
    with pytest.raises(ValueError, match="exactly one file"):
        _requirement(str(tmp_path / "liteyukibot_v7-*.whl"))


def test_target_version_is_an_alpha15_lockstep_identity() -> None:
    registry = resolve_workspace_registry(ROOT)
    assert {component.version for component in registry.components} == {"7.0.0a15"}
    assert re.search(r'version = "7\.0\.0a15"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
