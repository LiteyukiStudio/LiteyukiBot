"""Run the standalone Broker verifier against workspace wheels."""

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
    wheels = {
        "kernel": tuple((ROOT / "dist" / "workspace").glob("liteyukibot_v7_kernel-*-py3-none-any.whl")),
        "broker": tuple((ROOT / "dist" / "workspace").glob("liteyukibot_v7_broker-*-py3-none-any.whl")),
    }
    if any(len(paths) != 1 for paths in wheels.values()):
        raise RuntimeError(f"expected one kernel and one Broker wheel, found {wheels}")
    command = [uv, "run", "--no-project", "--python", "3.14"]
    for paths in wheels.values():
        command.extend(("--with", str(paths[0].resolve())))
    command.extend(("python", str(ROOT / "scripts" / "verify_broker_install.py")))
    with tempfile.TemporaryDirectory(prefix="liteyuki-broker-install-") as directory:
        subprocess.run(command, cwd=directory, env=_clean_environment(os.environ), check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
