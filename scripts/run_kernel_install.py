"""Run the standalone kernel verifier against its workspace wheel."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.run_isolated_install import _clean_environment

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv executable was not found")
    wheels = tuple((ROOT / "dist" / "workspace").glob("liteyukibot_v7_kernel-*-py3-none-any.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one kernel wheel in dist/workspace, found {len(wheels)}")
    command = [
        uv,
        "run",
        "--no-project",
        "--python",
        "3.14",
        "--with",
        str(wheels[0].resolve()),
        "python",
        str(ROOT / "scripts" / "verify_kernel_install.py"),
    ]
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(command, cwd=directory, env=_clean_environment(os.environ), check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
