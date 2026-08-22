"""Command line entry point for the independent LiteyukiBot developer tool."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from liteyukibot.bundles import (
    BUNDLE_MANIFEST_NAME,
    BUNDLE_TAG,
    BundleError,
    SignatureVerifier,
    VerifiedBundle,
    requirements_from_lock,
    sha256_file,
    verify_bundle,
)
from liteyukibot.config import CONFIG_VERSION, ConfigurationError, ConfigWorkspace
from liteyukibot.exceptions import LiteyukiError
from liteyukibot.profiles import ProfileError, ProfileManifest, ProfileStore


def build_parser() -> argparse.ArgumentParser:
    """Build parser.

    Returns:
        The `argparse.ArgumentParser` result produced by the operation.
    """
    parser = argparse.ArgumentParser(prog="liteyuki-dev")
    parser.add_argument("--workspace", default=".", metavar="PATH")
    parser.add_argument("--instance", default="default", metavar="NAME")
    commands = parser.add_subparsers(dest="command", required=True)

    verify = commands.add_parser("verify", help="verify a signed local release bundle")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--tag", default=BUNDLE_TAG)

    stage = commands.add_parser("stage", help="stage a verified bundle into an offline profile")
    stage.add_argument("--bundle", type=Path, required=True)
    stage.add_argument("--python", default="3.14")
    stage.add_argument("--uv", default="uv", dest="uv_command")

    update = commands.add_parser("update", help="stage and ask the owning daemon to update an instance")
    update.add_argument("--bundle", type=Path, required=True)
    update.add_argument("--python", default="3.14")
    update.add_argument("--uv", default="uv", dest="uv_command")

    commands.add_parser("status", help="show profiles and the current instance update state")
    commands.add_parser("rollback", help="ask the owning daemon to roll back the active profile")

    lyf = commands.add_parser("lyf", help="read-only LYF diagnostics")
    lyf_commands = lyf.add_subparsers(dest="lyf_command", required=True)
    diagnose = lyf_commands.add_parser("diagnose")
    diagnose.add_argument("paths", nargs="*", type=Path)
    diagnose.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line entry point.

    Args:
        argv: The argv value used by the operation.

    Returns:
        The `int` result produced by the operation.
    """
    args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        workspace = Path(args.workspace).resolve()
        if args.command == "verify":
            verified = verify_bundle(args.bundle.resolve(), tag=args.tag)
            _print_verified(verified)
            return 0
        if args.command == "stage":
            profile_id = stage_bundle(
                workspace,
                args.bundle.resolve(),
                python_version=args.python,
                uv_command=args.uv_command,
            )
            print(profile_id)
            return 0
        if args.command == "update":
            profile_id = stage_bundle(
                workspace,
                args.bundle.resolve(),
                python_version=args.python,
                uv_command=args.uv_command,
            )
            return _request_daemon(workspace, args.instance, "update", {"profile_id": profile_id})
        if args.command == "status":
            return _status(workspace, args.instance)
        if args.command == "rollback":
            return _request_daemon(workspace, args.instance, "rollback", {})
        if args.command == "lyf" and args.lyf_command == "diagnose":
            return _diagnose(args.paths, args.json_output)
    except (BundleError, ConfigurationError, LiteyukiError, ProfileError, OSError, RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    raise RuntimeError("unreachable developer command")


def _print_verified(verified: VerifiedBundle) -> None:
    """Implement the print verified operation for the component.

    Args:
        verified: The verified value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_print_verified`. It delegates to `print`, `dumps`,
        `requirements_from_lock` while keeping intermediate state local to the owning operation.
    """
    print(
        json.dumps(
            {
                "verified": True,
                "tag": verified.release_tag,
                "version": verified.release_version,
                "artifacts": len(verified.artifact_records),
                "requirements": len(requirements_from_lock(verified)),
                "manifest": str(verified.root / BUNDLE_MANIFEST_NAME),
            },
            sort_keys=True,
        )
    )


def _write_requirements(path: Path, requirements: Sequence[str]) -> None:
    """Write requirements.

    Args:
        path: Filesystem or logical resource path.
        requirements: The requirements value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_write_requirements`. It delegates to `write_text`, `join`
        while keeping intermediate state local to the owning operation.
    """
    path.write_text("".join(f"{requirement}\n" for requirement in requirements), encoding="utf-8")


def stage_bundle(
    workspace: Path,
    bundle: Path,
    *,
    python_version: str,
    uv_command: str,
    signature_verifier: SignatureVerifier | None = None,
) -> str:
    """Verify and install a bundle using only files from its own directory.

    Args:
        workspace: The workspace value used by the operation.
        bundle: The bundle value used by the operation.
        python_version: The python version value used by the operation.
        uv_command: The uv command value used by the operation.
        signature_verifier: The signature verifier value used by the operation.

    Returns:
        The `str` result produced by the operation.
    """

    verified = verify_bundle(bundle, signature_verifier=signature_verifier)
    requirements = requirements_from_lock(verified)
    if not requirements:
        raise BundleError("bundle dependency lock has no install requirements")
    store = ProfileStore(workspace)
    profile_id, profile = store.create(tuple(requirements))
    python = ProfileStore.python_path(profile)
    requirements_path = profile / "bundle-requirements.txt"
    _write_requirements(requirements_path, requirements)
    environment = {**os.environ, "LITEYUKI_PROFILE_STAGE": "1"}
    try:
        _run(
            [uv_command, "venv", "--python", python_version, str(profile / "venv")],
            cwd=workspace,
            env=environment,
        )
        _run(
            [
                uv_command,
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(bundle),
                "--python",
                str(python),
                "--requirement",
                str(requirements_path),
            ],
            cwd=workspace,
            env=environment,
        )
        installed = _installed_report(python, cwd=workspace, env=environment)
        manifest = ProfileManifest(
            id=profile_id,
            created_at=datetime.now(UTC).isoformat(),
            requirements=tuple(requirements),
            python=str(installed["python"]),
            distributions={str(name): str(version) for name, version in dict(installed["distributions"]).items()},
            direct_urls=ProfileManifest.sanitize_direct_urls(dict(installed.get("direct_urls", {}))),
            config_version=CONFIG_VERSION,
            bundle_tag=verified.release_tag,
            bundle_version=verified.release_version,
            bundle_manifest_sha256=sha256_file(bundle / BUNDLE_MANIFEST_NAME),
            dependency_lock_sha256=_lock_digest(verified),
            artifact_filenames=tuple(
                str(record["filename"])
                for record in verified.artifact_records
                if isinstance(record.get("filename"), str)
            ),
        )
        store.write_manifest(manifest)
        requirements_path.unlink(missing_ok=True)
    except BaseException:
        shutil.rmtree(profile, ignore_errors=True)
        raise
    return profile_id


def _run(command: Sequence[str], *, cwd: Path, env: dict[str, str]) -> None:
    """Run the component operation.

    Args:
        command: Command or operation name to execute.
        cwd: The cwd value used by the operation.
        env: The env value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_run`. It delegates to `run` while keeping intermediate
        state local to the owning operation.
    """
    subprocess.run(list(command), cwd=cwd, env=env, check=True)


def _lock_digest(verified: VerifiedBundle) -> str:
    """Implement the lock digest operation for the component.

    Args:
        verified: The verified value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_lock_digest`. It delegates to `get` while keeping
        intermediate state local to the owning operation.
    """
    reference = verified.manifest.get("dependency_lock")
    if not isinstance(reference, dict) or not isinstance(reference.get("sha256"), str):
        raise BundleError("verified bundle has no dependency lock digest")
    digest = reference.get("sha256")
    assert isinstance(digest, str)
    return digest


def _installed_report(python: Path, *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    """Implement the installed report operation for the component.

    Args:
        python: The python value used by the operation.
        cwd: The cwd value used by the operation.
        env: The env value used by the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_installed_report`. It delegates to `run`, `loads` while
        keeping intermediate state local to the owning operation.
    """
    source = (
        "import importlib.metadata as m, json, sys; "
        "items = {d.metadata['Name'].lower(): d.version for d in m.distributions() if d.metadata.get('Name')}; "
        "urls = {d.metadata['Name'].lower(): json.loads(raw) for d in m.distributions() "
        "if d.metadata.get('Name') and (raw := d.read_text('direct_url.json'))}\n"
        "print(json.dumps({'python': sys.executable, 'distributions': items, 'direct_urls': urls}, sort_keys=True))"
    )
    completed = subprocess.run(
        [str(python), "-c", source],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ProfileError("staged Python returned an invalid distribution report")
    return value


def _config_version(workspace: Path) -> int:
    """Implement the config version operation for the component.

    Args:
        workspace: The workspace value used by the operation.

    Returns:
        The `int` result produced by the operation.

    Notes:
        Internal implementation detail for `_config_version`. It delegates to `is_file`, `loads`,
        `read_text`, `get` while keeping intermediate state local to the owning operation.
    """
    path = ConfigWorkspace(workspace).path
    if not path.is_file():
        return CONFIG_VERSION
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    value = document.get("config_version")
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError("migration_required: configuration has no supported config_version")
    return value


def _request_daemon(workspace: Path, instance: str, operation: str, payload: dict[str, object]) -> int:
    """Request daemon.

    Args:
        workspace: The workspace value used by the operation.
        instance: The instance value used by the operation.
        operation: The operation value used by the operation.
        payload: JSON-safe payload carried by the operation.

    Returns:
        The `int` result produced by the operation.

    Notes:
        Internal implementation detail for `_request_daemon`. It delegates to `_config_version`,
        `from_workspace`, `is_file`, `get` while keeping intermediate state local to the owning
        operation.
    """
    from liteyukibot.control import ControlError, request_control
    from liteyukibot.instances import InstancePaths

    if operation in {"update", "rollback"} and _config_version(workspace) != CONFIG_VERSION:
        raise RuntimeError(
            f"migration_required: active configuration must be v{CONFIG_VERSION} before {operation}"
        )
    paths = InstancePaths.from_workspace(ConfigWorkspace(workspace), instance)
    descriptor = paths.daemon_descriptor
    if not descriptor.is_file():
        raise ControlError(f"managed instance {instance!r} is not running under InstanceDaemon")
    if operation == "update":
        profile_id = payload.get("profile_id")
        if not isinstance(profile_id, str):
            raise ValueError("update requires a staged profile id")
        result = asyncio.run(request_control(descriptor, operation, profile_id=profile_id))
    else:
        result = asyncio.run(request_control(descriptor, operation))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def _status(workspace: Path, instance: str) -> int:
    """Return the status of the component operation.

    Args:
        workspace: The workspace value used by the operation.
        instance: The instance value used by the operation.

    Returns:
        The `int` result produced by the operation.

    Notes:
        Internal implementation detail for `_status`. It delegates to `active`, `document`,
        `from_workspace`, `is_file` while keeping intermediate state local to the owning operation.
    """
    store = ProfileStore(workspace)
    payload: dict[str, object] = {
        "active": store.active(),
        "profiles": [manifest.document() for manifest in store.list()],
        "instance": instance,
    }
    try:
        from liteyukibot.control import request_control
        from liteyukibot.instances import InstancePaths

        descriptor = InstancePaths.from_workspace(ConfigWorkspace(workspace), instance).daemon_descriptor
        if descriptor.is_file():
            payload["daemon"] = asyncio.run(request_control(descriptor, "status"))
    except (OSError, RuntimeError, ValueError, LiteyukiError) as error:
        payload["daemon_error"] = str(error)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _diagnose(paths: Sequence[Path], json_output: bool) -> int:
    """Implement the diagnose operation for the component.

    Args:
        paths: The paths value used by the operation.
        json_output: The json output value used by the operation.

    Returns:
        The `int` result produced by the operation.

    Notes:
        Internal implementation detail for `_diagnose`. It delegates to `read`, `read_text`, `parse`,
        `extend` while keeping intermediate state local to the owning operation.
    """
    from liteyukibot_functions import parse

    selected = tuple(paths) or (Path("-"),)
    diagnostics: list[dict[str, object]] = []
    for path in selected:
        source = sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8")
        result = parse(source, source_id=str(path))
        diagnostics.extend(item.as_dict() for item in result.diagnostics)
    if json_output:
        print(
            json.dumps(
                {"diagnostics": diagnostics, "ok": not any(item["severity"] == "error" for item in diagnostics)},
                sort_keys=True,
            )
        )
    else:
        for item in diagnostics:
            print(f"{item['source']}: {item['severity']}: {item['code']}: {item['message']}")
        if not diagnostics:
            print("LYF diagnostics: no issues")
    return 1 if any(item["severity"] == "error" for item in diagnostics) else 0


__all__ = ["build_parser", "main", "stage_bundle"]
