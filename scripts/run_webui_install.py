"""Verify the staged WebUI wheel outside the source checkout."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    wheels = tuple((ROOT / "dist" / "workspace").glob("liteyukibot_v7_webui-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one WebUI wheel, found {len(wheels)}")
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
            "--verifier",
            "scripts/verify_webui_install.py",
        ],
        check=True,
        cwd=ROOT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
