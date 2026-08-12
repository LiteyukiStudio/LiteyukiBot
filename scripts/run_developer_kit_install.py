"""Run the developer-kit verifier with the wheels built in this checkout."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from scripts.run_isolated_install import _clean_environment

ROOT = Path(__file__).resolve().parents[1]


def _build_dir() -> Path:
    return Path(os.environ.get("LITEYUKI_BUILD_DIR", ROOT / "dist")).resolve()


def _one_wheel(directory: Path, distribution: str) -> Path:
    matches = tuple(directory.glob(f"{distribution}-*-py3-none-any.whl"))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one {distribution} wheel in {directory}, found {len(matches)}"
        )
    return matches[0].resolve()


def main() -> int:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv executable was not found")
    build_dir = _build_dir()
    wheels = (
        _one_wheel(build_dir, "liteyukibot_v7"),
        _one_wheel(build_dir / "examples", "liteyukibot_example_plugin"),
        _one_wheel(build_dir / "examples", "liteyukibot_example_runtime"),
    )
    command = [uv, "run", "--no-project", "--python", "3.14"]
    for wheel in wheels:
        command.extend(("--with", str(wheel)))
    command.extend(("python", str(ROOT / "scripts" / "verify_developer_kit_install.py")))
    subprocess.run(command, cwd=ROOT, env=_clean_environment(os.environ), check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
