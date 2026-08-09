"""Validate the source release identity before building or publishing."""

from __future__ import annotations

import argparse
import json
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

EXPECTED_DISTRIBUTION = "liteyukibot-v7"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class ReleaseIdentity:
    distribution: str
    version: str


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


def validate_release(identity: ReleaseIdentity, *, tag: str | None = None) -> None:
    if identity.distribution != EXPECTED_DISTRIBUTION:
        raise RuntimeError(
            f"expected project.name={EXPECTED_DISTRIBUTION!r}, got {identity.distribution!r}"
        )
    if tag is not None:
        expected_tag = f"v{identity.version}"
        if tag != expected_tag:
            raise RuntimeError(f"expected release tag {expected_tag!r}, got {tag!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=PROJECT_ROOT / "pyproject.toml")
    parser.add_argument("--tag")
    args = parser.parse_args()

    identity = read_release_identity(args.project)
    validate_release(identity, tag=args.tag)
    print(json.dumps(asdict(identity), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
