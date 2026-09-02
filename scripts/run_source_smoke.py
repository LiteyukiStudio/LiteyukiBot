"""Exercise the editable source checkout through the public CLI."""

from __future__ import annotations

import asyncio
import importlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import ModuleType

from liteyukibot import LiteyukiApp
from liteyukibot.config import ConfigWorkspace, load_settings

ROOT = Path(__file__).resolve().parents[1]
_ISOLATION_VARIABLES = (
    "VIRTUAL_ENV",
    "PYTHONPATH",
    "UV_PROJECT_ENVIRONMENT",
    "UV_WORKING_DIRECTORY",
)


def _clean_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in _ISOLATION_VARIABLES:
        environment.pop(name, None)
    return environment


def _uv_command(uv: str, *arguments: str) -> list[str]:
    return [
        uv,
        "run",
        "--project",
        str(ROOT),
        "--locked",
        "--no-sync",
        *arguments,
    ]


def _run(command: list[str], *, cwd: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, env=environment, text=True, capture_output=True)
    if result.returncode != 0:
        details = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise RuntimeError(f"source smoke command failed ({result.returncode}): {' '.join(command)}\n{details}")
    return result


def _run_cli(
    uv: str,
    arguments: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return _run(_uv_command(uv, "liteyuki", *arguments), cwd=cwd, environment=environment)


def _assert_source_module(module_name: str) -> None:
    module: ModuleType = importlib.import_module(module_name)
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        raise RuntimeError(f"{module_name} has no importable source file")
    path = Path(module_file).resolve()
    if ROOT not in path.parents:
        raise RuntimeError(f"{module_name} was not imported from the source checkout: {path}")


async def _exercise_app(workspace: Path) -> None:
    config = ConfigWorkspace(workspace).path
    settings = load_settings(config, environ={})
    app = LiteyukiApp(settings, resource_workspace=workspace)
    await app.start()
    try:
        if app.status()["state"] != "ready":
            raise RuntimeError(f"application did not become ready: {app.status()}")
    finally:
        await app.stop()
    if app.status()["state"] != "stopped":
        raise RuntimeError(f"application did not stop cleanly: {app.status()}")


def run() -> None:
    """Run the source checkout smoke in a disposable instance directory."""
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv executable was not found")
    _assert_source_module("liteyukibot")
    _assert_source_module("liteyukibot_kernel")
    _assert_source_module("liteyukibot_cordis")
    _assert_source_module("liteyukibot_adapter_onebot")

    environment = _clean_environment()
    with tempfile.TemporaryDirectory(prefix="liteyuki-source-smoke-") as directory:
        root = Path(directory)
        workspace = root / "instance"
        _run_cli(
            uv,
            ["--workspace", str(workspace), "init", "--locale", "en-US"],
            cwd=root,
            environment=environment,
        )
        _run_cli(
            uv,
            ["check", "--workspace", str(workspace), "--format", "json"],
            cwd=root,
            environment=environment,
        )
        _run_cli(
            uv,
            ["config", "show", "--workspace", str(workspace), "--format", "json"],
            cwd=root,
            environment=environment,
        )
        asyncio.run(_exercise_app(workspace))


def main() -> int:
    run()
    print("source smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
