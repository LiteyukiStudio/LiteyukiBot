"""Verify the staged WebUI wheel outside the source checkout."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workspace = ROOT / "dist" / "workspace"
    wheels = tuple(workspace.glob("liteyukibot_v7_webui-*.whl"))
    root_wheels = tuple(workspace.glob("liteyukibot_v7-*-py3-none-any.whl"))
    kernel_wheels = tuple(workspace.glob("liteyukibot_v7_kernel-*-py3-none-any.whl"))
    if len(wheels) != 1 or len(root_wheels) != 1 or len(kernel_wheels) != 1:
        raise RuntimeError(
            "expected one WebUI, root, and kernel wheel, found "
            f"{len(wheels)}, {len(root_wheels)}, and {len(kernel_wheels)}"
        )
    subprocess.run(
        [
            "uv",
            "run",
            "--no-project",
            "--python",
            "3.14",
            "python",
            "scripts/run_isolated_install.py",
            "--with",
            str(wheels[0]),
            "--with",
            str(kernel_wheels[0]),
            "--with",
            str(root_wheels[0]),
            "--verifier",
            "scripts/verify_webui_install.py",
        ],
        check=True,
        cwd=ROOT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
