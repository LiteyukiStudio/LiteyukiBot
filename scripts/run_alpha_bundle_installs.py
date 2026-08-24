"""Exercise every current Alpha lockstep wheel from a staged bundle."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from scripts.alpha_release import ALPHA_VERSION, MANIFEST_NAME, AlphaReleaseError
from scripts.run_isolated_install import _clean_environment

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class InstallVerification:
    name: str
    distributions: tuple[str, ...]
    verifier: str
    arguments: tuple[str, ...] = ()


VERIFICATIONS: tuple[InstallVerification, ...] = (
    InstallVerification(
        "kernel",
        ("liteyukibot-v7",),
        "scripts/verify_published_install.py",
        ("--expected-version", ALPHA_VERSION, "--expect-no-legacy-runtime"),
    ),
    InstallVerification(
        "permissions", ("liteyukibot-v7", "liteyukibot-v7-permissions"), "scripts/verify_permissions_install.py"
    ),
    InstallVerification(
        "commands", ("liteyukibot-v7", "liteyukibot-v7-permissions", "liteyukibot-v7-commands"),
        "scripts/verify_commands_install.py",
    ),
    InstallVerification(
        "resources",
        ("liteyukibot-v7", "liteyukibot-v7-permissions", "liteyukibot-v7-commands", "liteyukibot-v7-resources"),
        "scripts/verify_resources_install.py",
    ),
    InstallVerification(
        "profile",
        (
            "liteyukibot-v7",
            "liteyukibot-v7-permissions",
            "liteyukibot-v7-commands",
            "liteyukibot-v7-resources",
            "liteyukibot-v7-profile",
        ),
        "scripts/verify_profile_install.py",
    ),
    InstallVerification(
        "essentials",
        ("liteyukibot-v7", "liteyukibot-v7-permissions", "liteyukibot-v7-commands", "liteyukibot-v7-essentials"),
        "scripts/verify_essentials_install.py",
    ),
    InstallVerification(
        "agent-resolver",
        ("liteyukibot-v7", "liteyukibot-v7-agent-resolver"),
        "scripts/verify_agent_resolver_install.py",
    ),
    InstallVerification(
        "functions", ("liteyukibot-v7", "liteyukibot-v7-functions"), "scripts/verify_functions_install.py"
    ),
    InstallVerification("cordis", ("liteyukibot-v7", "liteyukibot-v7-cordis"), "scripts/verify_cordis_install.py"),
    InstallVerification(
        "nonebot-bridge",
        ("liteyukibot-v7", "liteyukibot-v7-runtime-nonebot"),
        "scripts/verify_nonebot_runtime_install.py",
        ("--expected-version", ALPHA_VERSION),
    ),
    InstallVerification(
        "nonebot-api",
        ("liteyukibot-v7", "liteyukibot-v7-runtime-nonebot-api"),
        "scripts/verify_nonebot_api_install.py",
        ("--expected-version", ALPHA_VERSION),
    ),
    InstallVerification(
        "astrbot-bridge",
        ("liteyukibot-v7", "liteyukibot-v7-runtime-astrbot"),
        "scripts/verify_astrbot_runtime_install.py",
        ("--expected-version", ALPHA_VERSION),
    ),
    InstallVerification(
        "adapter-bridge",
        ("liteyukibot-v7", "liteyukibot-v7-runtime-adapter"),
        "scripts/verify_adapter_runtime_install.py",
        ("--expected-version", ALPHA_VERSION),
    ),
    InstallVerification("webui", ("liteyukibot-v7-webui",), "scripts/verify_webui_install.py"),
    InstallVerification("ipc-native", ("liteyukibot-v7-ipc-native",), "scripts/verify_ipc_native_install.py"),
    InstallVerification(
        "astrbot-api",
        ("liteyukibot-v7", "liteyukibot-v7-runtime-astrbot-api"),
        "scripts/verify_astrbot_api_install.py",
        ("--expected-version", ALPHA_VERSION),
    ),
    InstallVerification(
        "devcli",
        ("liteyukibot-v7", "liteyukibot-v7-functions", "liteyukibot-v7-devcli"),
        "scripts/verify_devcli_install.py",
        ("--expected-version", ALPHA_VERSION),
    ),
)


def _manifest(bundle: Path) -> list[Mapping[str, object]]:
    try:
        document = json.loads((bundle / MANIFEST_NAME).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise AlphaReleaseError("cannot read Alpha bundle manifest") from error
    artifacts = document.get("artifacts") if isinstance(document, dict) else None
    if not isinstance(artifacts, list) or not all(isinstance(item, dict) for item in artifacts):
        raise AlphaReleaseError("Alpha bundle manifest has invalid artifacts")
    return [cast(Mapping[str, object], item) for item in artifacts]


def _native_wheel(candidates: Sequence[Path]) -> Path:
    if len(candidates) == 1:
        return candidates[0]
    if sys.platform == "win32":
        markers = ("win_amd64", "win32")
    elif sys.platform == "darwin":
        markers = ("macosx",)
    else:
        markers = ("manylinux", "linux_")
    matching = tuple(path for path in candidates if any(marker in path.name.lower() for marker in markers))
    if len(matching) != 1:
        raise AlphaReleaseError(f"bundle has no unique native wheel for {sys.platform}")
    return matching[0]


def wheels_for(bundle: Path, distribution: str) -> tuple[Path, ...]:
    """Return the staged wheels suitable for one verifier on this platform."""

    candidates: list[Path] = []
    for record in _manifest(bundle):
        if record.get("distribution") != distribution or record.get("kind") != "wheel":
            continue
        filename = record.get("filename")
        if not isinstance(filename, str):
            raise AlphaReleaseError("Alpha bundle artifact filename is invalid")
        wheel = bundle / filename
        if not wheel.is_file():
            raise AlphaReleaseError(f"Alpha bundle wheel is missing: {filename}")
        candidates.append(wheel)
    if not candidates:
        raise AlphaReleaseError(f"Alpha bundle is missing a wheel for {distribution}")
    if distribution == "liteyukibot-v7-ipc-native":
        return (_native_wheel(candidates),)
    if len(candidates) != 1:
        raise AlphaReleaseError(f"Alpha bundle has multiple wheels for {distribution}")
    return tuple(candidates)


def command_for(bundle: Path, verification: InstallVerification, uv: str) -> list[str]:
    command = [
        uv,
        "run",
        "--no-project",
        "--python",
        "3.14",
        "--no-index",
        "--find-links",
        str(bundle.resolve()),
    ]
    for distribution in verification.distributions:
        for wheel in wheels_for(bundle, distribution):
            command.extend(("--with", str(wheel.resolve())))
    command.extend(("python", str((ROOT / verification.verifier).resolve()), *verification.arguments))
    return command


def run(bundle: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv executable was not found")
    environment = _clean_environment(os.environ)
    with tempfile.TemporaryDirectory(prefix="liteyuki-alpha-bundle-") as directory:
        for verification in VERIFICATIONS:
            subprocess.run(command_for(bundle, verification, uv), cwd=directory, env=environment, check=True)
        reference_wheel = wheels_for(bundle, "liteyukibot-v7-example-nonebot-plugin")[0]
        e2e_command = [
            uv,
            "run",
            "--no-project",
            "--python",
            "3.14",
            "--no-index",
            "--find-links",
            str(bundle.resolve()),
            "--with",
            str(wheels_for(bundle, "liteyukibot-v7")[0].resolve()),
            "--with",
            str(wheels_for(bundle, "liteyukibot-v7-runtime-nonebot")[0].resolve()),
            "--with",
            str(reference_wheel.resolve()),
            "python",
            str((ROOT / "scripts" / "run_nonebot_plugin_e2e.py").resolve()),
            "--wheel-dir",
            str(bundle.resolve()),
            "--workspace",
            str((Path(directory) / "nonebot-e2e").resolve()),
        ]
        subprocess.run(e2e_command, cwd=directory, env=environment, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.bundle.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
