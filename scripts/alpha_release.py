"""Build and verify the signed, lockstep Alpha release bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import tarfile
import tomllib
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any, cast

from liteyukibot.bundles import (
    BUNDLE_BASELINE,
    BUNDLE_LOCK_NAME,
    BUNDLE_MANIFEST_NAME,
    BUNDLE_SBOM_NAME,
    BUNDLE_SIGNATURE_NAME,
    BUNDLE_TAG,
    BUNDLE_VERSION,
    BundleError,
)
from liteyukibot.bundles import (
    verify_bundle as verify_offline_bundle,
)


class AlphaReleaseError(BundleError):
    """Raised when an Alpha bundle does not satisfy its frozen contract."""


@dataclass(frozen=True, slots=True)
class AlphaComponent:
    """One distribution included in the current Alpha bundle."""

    component_id: str
    project_dir: str
    distribution: str
    requires_sdist: bool = True
    version: str | None = None
    reserved: bool = False

    @property
    def release_version(self) -> str:
        return self.version or ALPHA_VERSION


ALPHA_VERSION = BUNDLE_VERSION
ALPHA_TAG = BUNDLE_TAG
MANIFEST_NAME = BUNDLE_MANIFEST_NAME
LOCK_NAME = BUNDLE_LOCK_NAME
SBOM_NAME = BUNDLE_SBOM_NAME
SIGNATURE_NAME = BUNDLE_SIGNATURE_NAME
OIDC_ISSUER = "https://token.actions.githubusercontent.com"
WORKFLOW_PATH = ".github/workflows/alpha-release.yaml"
BASELINE: Mapping[str, int] = BUNDLE_BASELINE
LOCKSTEP_COMPONENTS: tuple[AlphaComponent, ...] = (
    AlphaComponent("kernel", ".", "liteyukibot-v7"),
    AlphaComponent("ipc-native", "packages/ipc-native", "liteyukibot-v7-ipc-native"),
    AlphaComponent("cordis", "packages/cordis", "liteyukibot-v7-cordis"),
    AlphaComponent("nonebot-bridge", "packages/runtime-nonebot", "liteyukibot-v7-runtime-nonebot"),
    AlphaComponent("nonebot-api", "packages/runtime-nonebot-api", "liteyukibot-v7-runtime-nonebot-api"),
    AlphaComponent("astrbot-bridge", "packages/runtime-astrbot", "liteyukibot-v7-runtime-astrbot"),
    AlphaComponent("astrbot-api", "packages/runtime-astrbot-api", "liteyukibot-v7-runtime-astrbot-api"),
    AlphaComponent("adapter-bridge", "packages/runtime-adapter", "liteyukibot-v7-runtime-adapter"),
    AlphaComponent("webui", "packages/webui", "liteyukibot-v7-webui"),
    AlphaComponent("devcli", "packages/devcli", "liteyukibot-v7-devcli", reserved=True),
)
INDEPENDENT_COMPONENTS: tuple[AlphaComponent, ...] = (
    AlphaComponent(
        "example-nonebot-plugin",
        "examples/nonebot-plugin",
        "liteyukibot-v7-example-nonebot-plugin",
        version="0.1.0",
    ),
    AlphaComponent("permissions", "packages/permissions", "liteyukibot-v7-permissions", version="0.3.0a2"),
    AlphaComponent("commands", "packages/commands", "liteyukibot-v7-commands", version="0.3.0a1"),
    AlphaComponent("resources", "packages/resources", "liteyukibot-v7-resources", version="0.2.0a1"),
    AlphaComponent("profile", "packages/profile", "liteyukibot-v7-profile", version="0.2.0a1"),
    AlphaComponent("essentials", "packages/essentials", "liteyukibot-v7-essentials", version="0.3.0a1"),
    AlphaComponent("agent-resolver", "packages/agent-resolver", "liteyukibot-v7-agent-resolver", version="0.2.0a1"),
    AlphaComponent("functions", "packages/functions", "liteyukibot-v7-functions", version="0.1.0a3"),
)
RELEASE_COMPONENTS = (
    tuple(component for component in LOCKSTEP_COMPONENTS if component.component_id != "devcli")
    + INDEPENDENT_COMPONENTS
    + (next(component for component in LOCKSTEP_COMPONENTS if component.component_id == "devcli"),)
)

SignatureVerifier = Callable[[Path, Path, str], None]


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project(root: Path, component: AlphaComponent) -> dict[str, Any]:
    project_file = root / component.project_dir / "pyproject.toml"
    try:
        document = tomllib.loads(project_file.read_text(encoding="utf-8"))
    except OSError as error:
        raise AlphaReleaseError(f"cannot read {project_file}") from error
    project = document.get("project")
    if not isinstance(project, dict):
        raise AlphaReleaseError(f"{project_file} does not contain a [project] table")
    return cast(dict[str, Any], project)


def _string_field(project: Mapping[str, Any], name: str, *, context: str) -> str:
    value = project.get(name)
    if not isinstance(value, str) or not value:
        raise AlphaReleaseError(f"{context} has no non-empty project.{name}")
    return value


def certificate_identity(tag: str = ALPHA_TAG) -> str:
    return f"https://github.com/LiteyukiStudio/LiteyukiBot/{WORKFLOW_PATH}@refs/tags/{tag}"


def validate_source_registry(root: Path) -> None:
    """Check that source metadata is exactly the current Alpha inventory."""

    for component in RELEASE_COMPONENTS:
        project = _project(root, component)
        context = str(Path(component.project_dir) / "pyproject.toml")
        if _string_field(project, "name", context=context) != component.distribution:
            raise AlphaReleaseError(f"{context} distribution does not match the Alpha registry")
        if _string_field(project, "version", context=context) != component.release_version:
            raise AlphaReleaseError(f"{context} must use Alpha version {component.release_version}")

    root_project = _project(root, LOCKSTEP_COMPONENTS[0])
    optional = root_project.get("optional-dependencies")
    webui_extra = optional.get("webui") if isinstance(optional, dict) else None
    if not isinstance(webui_extra, list) or f"liteyukibot-v7-webui[server]=={ALPHA_VERSION}" not in webui_extra:
        raise AlphaReleaseError("root webui extra must pin the Alpha WebUI wheel exactly")

    for component in RELEASE_COMPONENTS:
        if component.component_id in {"kernel", "ipc-native", "webui", "example-nonebot-plugin"}:
            continue
        project = _project(root, component)
        dependencies = project.get("dependencies")
        if not isinstance(dependencies, list) or f"liteyukibot-v7=={ALPHA_VERSION}" not in dependencies:
            raise AlphaReleaseError(f"{component.component_id} must pin liteyukibot-v7 to {ALPHA_VERSION}")


def _distribution_metadata(path: Path) -> tuple[str, str]:
    metadata_bytes: bytes
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = tuple(
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA") and name.count("/") == 1
            )
            if len(names) != 1:
                raise AlphaReleaseError(f"{path.name} has no unique wheel METADATA file")
            metadata_bytes = archive.read(names[0])
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            members = tuple(member for member in archive.getmembers() if member.name.endswith("/PKG-INFO"))
            preferred = tuple(member for member in members if ".egg-info/" not in member.name.lower())
            candidates = preferred or members
            if len(candidates) != 1:
                raise AlphaReleaseError(f"{path.name} has no unique source PKG-INFO file")
            extracted = archive.extractfile(candidates[0])
            if extracted is None:
                raise AlphaReleaseError(f"cannot read {path.name} PKG-INFO")
            metadata_bytes = extracted.read()
    else:
        raise AlphaReleaseError(f"unsupported release artifact {path.name}")
    message = BytesParser(policy=policy.default).parsebytes(metadata_bytes)
    name, version = message.get("Name"), message.get("Version")
    if not isinstance(name, str) or not isinstance(version, str) or not name or not version:
        raise AlphaReleaseError(f"{path.name} has invalid package metadata")
    return name, version


def _artifact_kind(path: Path) -> str:
    if path.suffix == ".whl":
        return "wheel"
    if path.name.endswith(".tar.gz"):
        return "sdist"
    raise AlphaReleaseError(f"unsupported release artifact {path.name}")


def _artifact_records(dist: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted(dist.iterdir()):
        if not path.is_file() or path.name in {MANIFEST_NAME, LOCK_NAME, SBOM_NAME, SIGNATURE_NAME}:
            continue
        if path.suffix != ".whl" and not path.name.endswith(".tar.gz"):
            continue
        distribution, version = _distribution_metadata(path)
        records.append(
            {
                "filename": path.name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "distribution": distribution,
                "version": version,
                "kind": _artifact_kind(path),
            }
        )
    return records


def _validate_artifact_set(records: Sequence[Mapping[str, object]]) -> None:
    expected = {component.distribution: component for component in RELEASE_COMPONENTS}
    observed: dict[str, set[str]] = {distribution: set() for distribution in expected}
    for record in records:
        distribution = record.get("distribution")
        version = record.get("version")
        kind = record.get("kind")
        if not isinstance(distribution, str) or not isinstance(version, str) or not isinstance(kind, str):
            raise AlphaReleaseError("manifest artifact has invalid metadata")
        if distribution in expected and version != expected[distribution].release_version:
            raise AlphaReleaseError(f"{distribution} artifact has the wrong Alpha version")
        if distribution in observed:
            observed[distribution].add(kind)
    for component in RELEASE_COMPONENTS:
        kinds = observed[component.distribution]
        if "wheel" not in kinds:
            raise AlphaReleaseError(f"bundle is missing a wheel for {component.distribution}")
        if component.requires_sdist and "sdist" not in kinds:
            raise AlphaReleaseError(f"bundle is missing a source distribution for {component.distribution}")


def create_manifest(root: Path, dist: Path) -> Path:
    """Write the exact canonical Alpha manifest for staged release artifacts."""

    validate_source_registry(root)
    records = _artifact_records(dist)
    _validate_artifact_set(records)
    components: list[dict[str, object]] = []
    for component in RELEASE_COMPONENTS:
        project = _project(root, component)
        components.append(
            {
                "id": component.component_id,
                "distribution": component.distribution,
                "version": component.release_version,
                "license": _string_field(project, "license", context=component.project_dir),
                "reserved": component.reserved,
                "independent": component in INDEPENDENT_COMPONENTS,
            }
        )
    lock_path = dist / LOCK_NAME
    if lock_path.exists():
        try:
            lock_payload = json.loads(lock_path.read_bytes())
        except (OSError, json.JSONDecodeError) as error:
            raise AlphaReleaseError("dependency lock is not valid JSON") from error
        if not isinstance(lock_payload, dict) or lock_payload.get("schema_version") != 1:
            raise AlphaReleaseError("dependency lock schema is unsupported")
        locked_records = lock_payload.get("artifacts")
        if not isinstance(locked_records, list) or not all(isinstance(record, dict) for record in locked_records):
            raise AlphaReleaseError("dependency lock artifacts are invalid")
        if {
            tuple(cast(dict[str, object], record).get(field) for field in ("filename", "bytes", "sha256"))
            for record in locked_records
        } != {
            tuple(record.get(field) for field in ("filename", "bytes", "sha256")) for record in records
        }:
            raise AlphaReleaseError("dependency lock does not cover the staged artifact set")
        if lock_path.read_bytes() != _canonical_json(lock_payload):
            raise AlphaReleaseError("dependency lock is not canonical UTF-8 JSON")
    else:
        lock_payload = {
            "schema_version": 1,
            "requirements": sorted(
                {
                    f"{record['distribution']}=={record['version']}"
                    for record in records
                    if record.get("kind") == "wheel"
                }
            ),
            "artifacts": records,
        }
        lock_path.write_bytes(_canonical_json(lock_payload))
    payload: dict[str, object] = {
        "schema_version": 1,
        "release": {"tag": ALPHA_TAG, "version": ALPHA_VERSION},
        "baseline": dict(BASELINE),
        "components": components,
        "artifacts": records,
        "dependency_lock": {
            "filename": LOCK_NAME,
            "bytes": lock_path.stat().st_size,
            "sha256": _sha256(lock_path),
        },
    }
    output = dist / MANIFEST_NAME
    output.write_bytes(_canonical_json(payload))
    return output


def create_sbom(dist: Path) -> Path:
    """Write a deterministic CycloneDX inventory for the manifest's component set."""

    manifest = _read_manifest(dist / MANIFEST_NAME)
    components = manifest["components"]
    records = manifest["artifacts"]
    assert isinstance(components, list) and isinstance(records, list)
    component_metadata = {
        item["distribution"]: item
        for item in components
        if isinstance(item, dict) and isinstance(item.get("distribution"), str)
    }
    bom_components: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict):
            raise AlphaReleaseError("manifest artifact is invalid")
        distribution, version = record.get("distribution"), record.get("version")
        if not isinstance(distribution, str) or not isinstance(version, str):
            raise AlphaReleaseError("manifest artifact identity is invalid")
        if (distribution, version) in seen:
            continue
        seen.add((distribution, version))
        component = component_metadata.get(distribution, {})
        license_value = component.get("license")
        license_entry = (
            {"name": license_value}
            if isinstance(license_value, str) and license_value.startswith("LicenseRef-")
            else {"id": license_value}
            if isinstance(license_value, str)
            else None
        )
        bom_components.append(
            {
                "type": "library",
                "name": distribution,
                "version": version,
                "licenses": [{"license": license_entry}] if license_entry is not None else [],
                "properties": [{"name": "liteyuki:reserved", "value": "true"}]
                if component.get("reserved")
                else [],
            }
        )
    payload = {"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1, "components": bom_components}
    output = dist / SBOM_NAME
    output.write_bytes(_canonical_json(payload))
    return output


def _read_manifest(path: Path) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise AlphaReleaseError(f"cannot read canonical manifest {path}") from error
    if not isinstance(value, dict) or raw != _canonical_json(value):
        raise AlphaReleaseError("manifest is not canonical UTF-8 JSON")
    return cast(dict[str, object], value)


def _verify_manifest_shape(manifest: Mapping[str, object], *, tag: str) -> list[Mapping[str, object]]:
    if manifest.get("schema_version") != 1 or manifest.get("baseline") != dict(BASELINE):
        raise AlphaReleaseError("manifest schema or frozen baseline does not match the current Alpha")
    release = manifest.get("release")
    if release != {"tag": tag, "version": ALPHA_VERSION}:
        raise AlphaReleaseError("manifest release tag or version is invalid")
    components = manifest.get("components")
    if not isinstance(components, list):
        raise AlphaReleaseError("manifest components are invalid")
    expected = {component.component_id: component.distribution for component in RELEASE_COMPONENTS}
    expected["devcli"] = "liteyukibot-v7-devcli"
    observed: dict[str, str] = {}
    for component in components:
        if not isinstance(component, dict):
            raise AlphaReleaseError("manifest component is invalid")
        component_id, distribution = component.get("id"), component.get("distribution")
        if not isinstance(component_id, str) or not isinstance(distribution, str):
            raise AlphaReleaseError("manifest component identity is invalid")
        observed[component_id] = distribution
    if observed != expected:
        raise AlphaReleaseError("manifest component inventory does not match the current Alpha")
    if len(components) != len(expected):
        raise AlphaReleaseError("manifest component inventory contains duplicates")
    expected_components = {component.component_id: component for component in RELEASE_COMPONENTS}
    for component in components:
        assert isinstance(component, dict)
        component_id = cast(str, component["id"])
        expected_version = (
            expected_components[component_id].release_version if component_id != "devcli" else ALPHA_VERSION
        )
        independent = component_id in {item.component_id for item in INDEPENDENT_COMPONENTS}
        if component.get("version") != expected_version or component.get("reserved") is not (component_id == "devcli"):
            raise AlphaReleaseError("manifest component version or reserved state is invalid")
        if component.get("independent") is not independent:
            raise AlphaReleaseError("manifest component independent state is invalid")
        if component_id != "devcli" and not isinstance(component.get("license"), str):
            raise AlphaReleaseError("manifest component license is invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not all(isinstance(record, dict) for record in artifacts):
        raise AlphaReleaseError("manifest artifacts are invalid")
    return [cast(Mapping[str, object], record) for record in artifacts]


def _run_sigstore(signature: Path, manifest: Path, tag: str, command: str) -> None:
    completed = subprocess.run(
        [
            *shlex.split(command),
            "verify",
            "identity",
            "--bundle",
            str(signature),
            "--cert-identity",
            certificate_identity(tag),
            "--cert-oidc-issuer",
            OIDC_ISSUER,
            str(manifest),
        ],
        check=False,
    )
    if completed.returncode != 0:
        raise AlphaReleaseError("Sigstore identity verification failed")


def verify_bundle(
    bundle: Path,
    *,
    tag: str = ALPHA_TAG,
    sigstore_command: str = "sigstore",
    signature_verifier: SignatureVerifier | None = None,
) -> None:
    """Verify a downloaded Alpha bundle without reading source metadata."""
    try:
        verified = verify_offline_bundle(
            bundle,
            tag=tag,
            sigstore_command=sigstore_command,
            signature_verifier=signature_verifier,
        )
        _validate_artifact_set(verified.artifact_records)
    except BundleError as error:
        raise AlphaReleaseError(str(error)) from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-source")
    check.add_argument("--root", type=Path, default=Path.cwd())
    generate = commands.add_parser("generate")
    generate.add_argument("--root", type=Path, default=Path.cwd())
    generate.add_argument("--dist", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--tag", default=ALPHA_TAG)
    verify.add_argument("--sigstore-command", default="sigstore")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "check-source":
        validate_source_registry(args.root.resolve())
        return 0
    if args.command == "generate":
        dist = args.dist.resolve()
        create_manifest(args.root.resolve(), dist)
        create_sbom(dist)
        return 0
    if args.command == "verify":
        verify_bundle(args.bundle.resolve(), tag=args.tag, sigstore_command=args.sigstore_command)
        return 0
    raise AssertionError(f"unexpected command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
