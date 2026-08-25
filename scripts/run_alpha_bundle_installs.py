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

try:
    from scripts.release_registry import ReleaseRegistryError, WorkspaceComponent, resolve_workspace_registry
except ModuleNotFoundError:  # pragma: no cover - exercised by direct script execution
    from release_registry import (  # type: ignore[import-not-found, no-redef]
        ReleaseRegistryError,
        WorkspaceComponent,
        resolve_workspace_registry,
    )
from scripts.run_isolated_install import _clean_environment

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class InstallVerification:
    name: str
    distributions: tuple[str, ...]
    verifier: str
    arguments: tuple[str, ...] = ()


try:
    _REGISTRY = resolve_workspace_registry(ROOT)
except ReleaseRegistryError as error:
    raise RuntimeError(str(error)) from error


def _verification_for(component: WorkspaceComponent) -> InstallVerification:
    policy = component.policy
    if policy.verifier is None:
        raise RuntimeError(f"component {component.component_id} has no isolated verifier")
    by_id = _REGISTRY.by_component_id
    try:
        distributions = tuple(by_id[component_id].distribution for component_id in policy.verifier_components)
    except KeyError as error:
        raise RuntimeError(f"component {component.component_id} references an unknown verifier component") from error
    arguments = list(policy.verifier_arguments)
    if policy.expected_version != "none":
        expected_version = ALPHA_VERSION if policy.expected_version == "lockstep" else component.release_version
        arguments[0:0] = ["--expected-version", expected_version]
    return InstallVerification(component.component_id, distributions, policy.verifier, tuple(arguments))


VERIFICATIONS: tuple[InstallVerification, ...] = tuple(
    _verification_for(component) for component in _REGISTRY.verification_components
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
        reference = _REGISTRY.reference_e2e_component
        reference_distributions = tuple(
            _REGISTRY.by_component_id[component_id].distribution
            for component_id in reference.policy.reference_e2e_components
        )
        e2e_command = [
            uv,
            "run",
            "--no-project",
            "--python",
            "3.14",
            "--no-index",
            "--find-links",
            str(bundle.resolve()),
        ]
        for distribution in reference_distributions:
            e2e_command.extend(("--with", str(wheels_for(bundle, distribution)[0].resolve())))
        e2e_command.extend(
            [
            "python",
            str((ROOT / "scripts" / "run_nonebot_plugin_e2e.py").resolve()),
            "--wheel-dir",
            str(bundle.resolve()),
            "--workspace",
            str((Path(directory) / "nonebot-e2e").resolve()),
            ]
        )
        subprocess.run(e2e_command, cwd=directory, env=environment, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.bundle.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
