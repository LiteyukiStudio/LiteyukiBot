"""Run the essentials verifier against wheels built from this workspace."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _one_wheel(distribution: str) -> Path:
    directory = ROOT / "dist" / "workspace"
    matches = tuple(directory.glob(f"{distribution}-*-py3-none-any.whl"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one {distribution} wheel in {directory}, found {len(matches)}")
    return matches[0].resolve()


def main() -> int:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv executable was not found")
    wheels = (
        _one_wheel("liteyukibot_v7"),
        _one_wheel("liteyukibot_v7_permissions"),
        _one_wheel("liteyukibot_v7_commands"),
        _one_wheel("liteyukibot_v7_essentials"),
    )
    command = [uv, "run", "--no-project", "--python", "3.14"]
    for wheel in wheels:
        command.extend(("--with", str(wheel)))
    command.extend(("python", str(ROOT / "scripts" / "verify_essentials_install.py")))
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(command, cwd=directory, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
