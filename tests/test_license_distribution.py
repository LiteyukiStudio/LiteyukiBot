from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LICENSE_FILES = ("LICENSE", "LICENSE.en", "LICENSE.zh-CN")
LSO_COMMON = "LicenseRef-LSO-Common-1.4"


def _project_table(project_file: Path) -> dict[str, object]:
    document = tomllib.loads(project_file.read_text(encoding="utf-8"))
    project = document.get("project")
    assert isinstance(project, dict)
    return project


def test_root_declares_complete_lso_common_license_set() -> None:
    project = _project_table(PROJECT_ROOT / "pyproject.toml")

    assert project["license"] == LSO_COMMON
    assert project["license-files"] == list(LICENSE_FILES)
    for name in LICENSE_FILES:
        assert (PROJECT_ROOT / name).is_file()


def test_package_license_files_match_the_root_distribution() -> None:
    root_contents = {name: (PROJECT_ROOT / name).read_bytes() for name in LICENSE_FILES}
    package_dirs = sorted(path.parent for path in (PROJECT_ROOT / "packages").glob("*/pyproject.toml"))
    package_dirs.append(PROJECT_ROOT / "examples" / "nonebot-plugin")

    for package_dir in package_dirs:
        project = _project_table(package_dir / "pyproject.toml")
        assert project["license"] == LSO_COMMON, package_dir.name
        assert project["license-files"] == list(LICENSE_FILES), package_dir.name
        for name, expected in root_contents.items():
            assert (package_dir / name).read_bytes() == expected, f"{package_dir.name}/{name}"
