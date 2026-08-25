from __future__ import annotations

import importlib.metadata
import re
import tomllib
from pathlib import Path

import pytest
from scripts.check_release import (
    RELEASE_PROJECTS,
    ReleaseIdentity,
    project_for_tag,
    read_release_identity,
    validate_release,
)
from scripts.run_developer_kit_install import _build_dir, _example_build_dir
from scripts.run_isolated_install import _clean_environment, _requirement

import liteyukibot
from liteyukibot.bundles import BUNDLE_TAG, BUNDLE_VERSION


def test_kernel_import_namespace_uses_distribution_version() -> None:
    expected = importlib.metadata.version("liteyukibot-v7")

    assert liteyukibot.__version__ == expected


@pytest.mark.parametrize("name", tuple(RELEASE_PROJECTS))
def test_current_release_identities_accept_exact_tags(name: str) -> None:
    project = RELEASE_PROJECTS[name]
    identity = read_release_identity(project.project_file)
    tag = BUNDLE_TAG if name == "root" else f"{project.tag_prefix}{identity.version}"

    validate_release(identity, project=project, tag=tag)
    assert identity.distribution == project.distribution
    assert project_for_tag(tag) == project


def test_workspace_first_party_dependencies_are_exactly_pinned() -> None:
    root = Path(__file__).parents[1]
    project_files = [
        root / "pyproject.toml",
        *sorted((root / "packages").glob("*/pyproject.toml")),
        root / "examples" / "nonebot-plugin" / "pyproject.toml",
    ]
    projects = [tomllib.loads(project_file.read_text(encoding="utf-8"))["project"] for project_file in project_files]
    expected_versions = {
        re.sub(r"[-_.]+", "-", project["name"]).lower(): project["version"] for project in projects
    }
    specs: list[str] = []
    for project in projects:
        specs.extend(spec for spec in project.get("dependencies", []) if spec.startswith("liteyukibot-v7"))
        optional = project.get("optional-dependencies", {})
        for group in optional.values():
            specs.extend(spec for spec in group if spec.startswith("liteyukibot-v7"))

    assert specs
    for specification in specs:
        match = re.fullmatch(r"([A-Za-z0-9._-]+)(?:\[[^]]+\])?==([^,;\s]+)", specification)
        assert match is not None, f"first-party dependency is not an exact pin: {specification}"
        normalized_name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
        assert match.group(2) == expected_versions[normalized_name]
    assert f"liteyukibot-v7=={BUNDLE_VERSION}" in specs


@pytest.mark.parametrize(
    ("identity", "project_name", "tag", "message"),
    [
        (ReleaseIdentity("liteyukibot", "7.0.0a5"), "root", None, "project.name"),
        (ReleaseIdentity("liteyukibot-v7", "7.0.0a5"), "root", "v7.0.0a3", "release tag"),
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


def test_release_identity_rejects_alpha_from_pypi_workflows() -> None:
    with pytest.raises(RuntimeError, match="signed GitHub bundle"):
        validate_release(
            ReleaseIdentity("liteyukibot-v7", "7.0.0a1"),
            project=RELEASE_PROJECTS["root"],
            tag="v7.0.0a1",
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


def test_isolated_install_preserves_package_extras_requirement() -> None:
    requirement = "liteyukibot-v7[webui]>=7.0.0a13,<8"

    assert _requirement(requirement) == requirement


def test_developer_kit_install_uses_an_explicit_build_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LITEYUKI_BUILD_DIR", str(tmp_path))

    assert _build_dir() == tmp_path.resolve()
    assert _example_build_dir() == (tmp_path / "examples").resolve()


def test_developer_kit_install_uses_ci_build_directories(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITEYUKI_BUILD_DIR", raising=False)
    root = Path(__file__).parents[1]

    assert _build_dir() == (root / "dist" / "workspace").resolve()
    assert _example_build_dir() == (root / "dist" / "examples").resolve()
