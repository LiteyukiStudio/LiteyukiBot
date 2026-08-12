"""Run the adapter runtime verifier against workspace-built wheels."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.run_isolated_install import _clean_environment

ROOT = Path(__file__).resolve().parents[1]


def _one_wheel(distribution: str) -> Path:
    matches = tuple((ROOT / "dist" / "workspace").glob(f"{distribution}-*-py3-none-any.whl"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one {distribution} wheel in dist/workspace, found {len(matches)}")
    return matches[0].resolve()


def main() -> int:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv executable was not found")
    command = [uv, "run", "--no-project", "--python", "3.14"]
    for wheel in (_one_wheel("liteyukibot_v7"), _one_wheel("liteyukibot_v7_runtime_adapter")):
        command.extend(("--with", str(wheel)))
    command.extend(("python", str(ROOT / "scripts" / "verify_adapter_runtime_install.py")))
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(command, cwd=directory, env=_clean_environment(os.environ), check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
