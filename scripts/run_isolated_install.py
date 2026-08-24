"""Run an installed-artifact verifier from a temporary non-project directory."""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path

_ISOLATION_VARIABLES = (
    "VIRTUAL_ENV",
    "PYTHONPATH",
    "UV_PROJECT_ENVIRONMENT",
    "UV_WORKING_DIRECTORY",
)


def _requirement(value: str) -> str:
    if not value:
        raise ValueError("install requirement must not be empty")
    if value.lower().endswith(".whl") and glob.has_magic(value):
        matches = tuple(Path(match) for match in glob.glob(value))
        if len(matches) != 1:
            raise ValueError(f"install requirement pattern must match exactly one file: {value}")
        value = str(matches[0])
    candidate = Path(value)
    if not candidate.exists():
        return value
    if not candidate.is_file():
        raise ValueError(f"local install requirement must be a file: {candidate}")
    return str(candidate.resolve())


def _clean_environment(environment: Mapping[str, str]) -> dict[str, str]:
    cleaned = dict(environment)
    for name in _ISOLATION_VARIABLES:
        cleaned.pop(name, None)
    return cleaned


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with", dest="requirements", action="append", required=True)
    parser.add_argument("--verifier", type=Path, required=True)
    parser.add_argument("verifier_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv executable was not found")
    verifier = args.verifier.resolve()
    if not verifier.is_file():
        raise ValueError(f"verifier must be a file: {verifier}")
    command = [uv, "run", "--no-project", "--python", "3.14"]
    for requirement in args.requirements:
        command.extend(("--with", _requirement(requirement)))
    verifier_args = args.verifier_args
    if verifier_args[:1] == ["--"]:
        verifier_args = verifier_args[1:]
    command.extend(("python", str(verifier), *verifier_args))
    environment = _clean_environment(os.environ)
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(command, cwd=directory, env=environment, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
