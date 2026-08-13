"""Run the Satori adapter verifier against workspace-built wheels."""

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
    for distribution in (
        "liteyukibot_v7",
        "liteyukibot_v7_runtime_adapter",
        "liteyukibot_v7_adapter_satori",
    ):
        command.extend(("--with", str(_one_wheel(distribution))))
    command.extend(("python", str(ROOT / "scripts" / "verify_satori_adapter_install.py")))
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(command, cwd=directory, env=_clean_environment(os.environ), check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
