"""Exercise the user-facing ``uv tool install`` path from a built root wheel."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.bundles import BUNDLE_VERSION
from scripts.run_isolated_install import _clean_environment

ROOT = Path(__file__).resolve().parents[1]


def _root_wheel() -> Path:
    wheels = tuple((ROOT / "dist" / "workspace").glob("liteyukibot_v7-*-py3-none-any.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one root wheel in dist/workspace, found {len(wheels)}")
    return wheels[0].resolve()


def _kernel_wheel() -> Path:
    wheels = tuple((ROOT / "dist" / "workspace").glob("liteyukibot_v7_kernel-*-py3-none-any.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one kernel wheel in dist/workspace, found {len(wheels)}")
    return wheels[0].resolve()


def _cordis_wheel() -> Path:
    wheels = tuple((ROOT / "dist" / "workspace").glob("liteyukibot_v7_cordis-*-py3-none-any.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one Cordis wheel in dist/workspace, found {len(wheels)}")
    return wheels[0].resolve()


def _adapter_onebot_wheel() -> Path:
    wheels = tuple((ROOT / "dist" / "workspace").glob("liteyukibot_v7_adapter_onebot-*-py3-none-any.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one OneBot adapter wheel in dist/workspace, found {len(wheels)}")
    return wheels[0].resolve()


def _run(command: list[str], *, cwd: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=environment, text=True, capture_output=True, check=True)


def main() -> int:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv executable was not found")
    with tempfile.TemporaryDirectory(prefix="liteyuki-tool-smoke-") as directory:
        root = Path(directory)
        tool_directory = root / "tools"
        workspace = root / "workspace"
        environment = _clean_environment(os.environ)
        environment["UV_TOOL_DIR"] = str(tool_directory)
        bin_directory = Path(_run([uv, "tool", "dir", "--bin"], cwd=root, environment=environment).stdout.strip())
        environment["PATH"] = os.pathsep.join((str(bin_directory), environment.get("PATH", "")))

        _run(
            [
                uv,
                "tool",
                "install",
                "--python",
                "3.14",
                "--force",
                "--with",
                str(_kernel_wheel()),
                "--with",
                str(_cordis_wheel()),
                "--with",
                str(_adapter_onebot_wheel()),
                str(_root_wheel()),
            ],
            cwd=root,
            environment=environment,
        )
        version = _run(["liteyuki", "version"], cwd=root, environment=environment).stdout.strip()
        if version != BUNDLE_VERSION:
            raise RuntimeError(f"installed liteyuki CLI reported {version!r}; expected {BUNDLE_VERSION!r}")
        _run(
            ["liteyuki", "--workspace", str(workspace), "init", "--locale", "en-US"],
            cwd=root,
            environment=environment,
        )
        _run(["liteyuki", "--workspace", str(workspace), "check"], cwd=root, environment=environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
