"""Write release checksums and validate the project's declared license expression."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path

from license_expression import get_spdx_licensing  # type: ignore[import-untyped]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _license(project: dict[str, object]) -> str:
    value = project.get("license")
    if not isinstance(value, str) or not value:
        raise RuntimeError("project.license must be a non-empty SPDX expression or LicenseRef")
    if value.startswith("LicenseRef-") and value.removeprefix("LicenseRef-").replace("-", "").isalnum():
        return value
    if get_spdx_licensing().validate(value).errors:
        raise RuntimeError(f"project.license is not a valid SPDX expression: {value}")
    return value


def generate(project_dir: Path, dist_dir: Path) -> Path:
    document = tomllib.loads((project_dir / "pyproject.toml").read_text(encoding="utf-8"))
    project = document.get("project")
    if not isinstance(project, dict):
        raise RuntimeError("pyproject.toml does not contain a [project] table")
    name, version = project.get("name"), project.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        raise RuntimeError("project name and version must be strings")
    artifacts = [path for path in sorted(dist_dir.iterdir()) if path.suffix in {".whl", ".gz"}]
    if not artifacts:
        raise RuntimeError(f"no distribution artifacts found in {dist_dir}")
    payload = {
        "schema_version": 1,
        "project": {"name": name, "version": version, "license": _license(project)},
        "artifacts": [
            {"filename": path.name, "sha256": _digest(path), "bytes": path.stat().st_size} for path in artifacts
        ],
    }
    output = dist_dir / "artifacts.manifest.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    args = parser.parse_args()
    print(generate(args.project, args.dist))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
