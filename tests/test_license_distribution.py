from __future__ import annotations

import tomllib
from pathlib import Path

from scripts.release_registry import resolve_workspace_registry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LICENSE_FILES = ("LICENSE", "LICENSE.en", "LICENSE.zh-CN")
LSO_COMMON = "LicenseRef-LSO-Common-1.4"


def _project_table(project_file: Path) -> dict[str, object]:
    document = tomllib.loads(project_file.read_text(encoding="utf-8"))
    project = document.get("project")
    assert isinstance(project, dict)
    return project


def test_target_distributions_declare_the_complete_lso_common_license_set() -> None:
    registry = resolve_workspace_registry(PROJECT_ROOT)
    root_contents = {name: (PROJECT_ROOT / name).read_bytes() for name in LICENSE_FILES}

    assert all((PROJECT_ROOT / name).is_file() for name in LICENSE_FILES)
    for component in registry.components:
        project_dir = PROJECT_ROOT / component.project_dir
        project = _project_table(project_dir / "pyproject.toml")
        assert project["license"] == LSO_COMMON, component.project_dir
        assert project["license-files"] == list(LICENSE_FILES), component.project_dir
        for name, expected in root_contents.items():
            assert (project_dir / name).read_bytes() == expected, f"{component.project_dir}/{name}"


def test_workspace_registry_has_no_external_source_distribution() -> None:
    registry = resolve_workspace_registry(PROJECT_ROOT)
    assert all(not component.project_dir.startswith("extras/") for component in registry.components)
