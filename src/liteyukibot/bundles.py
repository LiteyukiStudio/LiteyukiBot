"""Offline verification primitives for signed LiteyukiBot release bundles."""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import tarfile
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import cast

from .exceptions import LiteyukiError

BUNDLE_MANIFEST_NAME = "artifacts.manifest.json"
BUNDLE_LOCK_NAME = "dependencies.lock.json"
BUNDLE_SBOM_NAME = "sbom.cdx.json"
BUNDLE_SIGNATURE_NAME = "artifacts.manifest.sigstore.json"
BUNDLE_TAG = "v7.0.0a9"
BUNDLE_VERSION = "7.0.0a9"
BUNDLE_BASELINE: Mapping[str, int] = {
    "lyip": 2,
    "runtime_ipc": 7,
    "broker": 7,
    "configuration": 6,
}
BUNDLE_WORKFLOW_PATH = ".github/workflows/alpha-release.yaml"
BUNDLE_OIDC_ISSUER = "https://token.actions.githubusercontent.com"

SignatureVerifier = Callable[[Path, Path, str], None]


class BundleError(LiteyukiError):
    """Raised when a release bundle is not safe to stage offline."""


@dataclass(frozen=True, slots=True)
class VerifiedBundle:
    """The verified data needed by a staging operation."""

    root: Path
    manifest: Mapping[str, object]
    dependency_lock: Mapping[str, object]
    artifact_records: tuple[Mapping[str, object], ...]

    @property
    def release_tag(self) -> str:
        """Return the verified bundle's release tag.

        Returns:
            The `str` result produced by the operation.
        """
        release = self.manifest.get("release")
        if not isinstance(release, dict):
            raise BundleError("bundle manifest release tag is invalid")
        tag = release.get("tag")
        if not isinstance(tag, str):
            raise BundleError("bundle manifest release tag is invalid")
        return tag

    @property
    def release_version(self) -> str:
        """Return the verified bundle's release version.

        Returns:
            The `str` result produced by the operation.
        """
        release = self.manifest.get("release")
        if not isinstance(release, dict):
            raise BundleError("bundle manifest release version is invalid")
        version = release.get("version")
        if not isinstance(version, str):
            raise BundleError("bundle manifest release version is invalid")
        return version

    @property
    def requirements(self) -> tuple[str, ...]:
        """Return the verified bundle's requirements.

        Returns:
            The requested `tuple[str, ...]` value.
        """
        value = self.dependency_lock.get("requirements", ())
        if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            raise BundleError("dependency lock requirements are invalid")
        return tuple(value)


def canonical_json(value: object) -> bytes:
    """Serialize a JSON value in the format covered by signatures.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `bytes` result produced by the operation.
    """

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha256_file(path: Path) -> str:
    """Implement the sha256 file operation for the component.

    Args:
        path: Filesystem or logical resource path.

    Returns:
        The `str` result produced by the operation.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_canonical_json(path: Path) -> dict[str, object]:
    """Read canonical json.

    Args:
        path: Filesystem or logical resource path.

    Returns:
        The requested `dict[str, object]` value.
    """
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleError(f"cannot read canonical JSON {path.name}") from error
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise BundleError(f"{path.name} is not canonical UTF-8 JSON")
    return cast(dict[str, object], value)


def artifact_metadata(path: Path) -> tuple[str, str]:
    """Read distribution metadata without importing or installing the artifact.

    Args:
        path: Filesystem or logical resource path.

    Returns:
        The `tuple[str, str]` result produced by the operation.
    """

    try:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                names = tuple(
                    name
                    for name in archive.namelist()
                    if name.endswith(".dist-info/METADATA") and name.count("/") == 1
                )
                if len(names) != 1:
                    raise BundleError(f"{path.name} has no unique wheel METADATA file")
                metadata_bytes = archive.read(names[0])
        elif path.name.endswith(".tar.gz"):
            with tarfile.open(path, "r:gz") as archive:
                members = tuple(member for member in archive.getmembers() if member.name.endswith("/PKG-INFO"))
                preferred = tuple(member for member in members if ".egg-info/" not in member.name.lower())
                candidates = preferred or members
                if len(candidates) != 1:
                    raise BundleError(f"{path.name} has no unique source PKG-INFO file")
                extracted = archive.extractfile(candidates[0])
                if extracted is None:
                    raise BundleError(f"cannot read {path.name} PKG-INFO")
                metadata_bytes = extracted.read()
        else:
            raise BundleError(f"unsupported release artifact {path.name}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise BundleError(f"cannot read package metadata from {path.name}") from error
    message = BytesParser(policy=policy.default).parsebytes(metadata_bytes)
    distribution, version = message.get("Name"), message.get("Version")
    if not isinstance(distribution, str) or not distribution or not isinstance(version, str) or not version:
        raise BundleError(f"{path.name} has invalid package metadata")
    return distribution, version


def artifact_kind(path: Path) -> str:
    """Implement the artifact kind operation for the component.

    Args:
        path: Filesystem or logical resource path.

    Returns:
        The `str` result produced by the operation.
    """
    if path.suffix == ".whl":
        return "wheel"
    if path.name.endswith(".tar.gz"):
        return "sdist"
    raise BundleError(f"unsupported release artifact {path.name}")


def artifact_record(path: Path) -> dict[str, object]:
    """Implement the artifact record operation for the component.

    Args:
        path: Filesystem or logical resource path.

    Returns:
        The `dict[str, object]` result produced by the operation.
    """
    distribution, version = artifact_metadata(path)
    return {
        "filename": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "distribution": distribution,
        "version": version,
        "kind": artifact_kind(path),
    }


def artifact_records(bundle: Path) -> tuple[Mapping[str, object], ...]:
    """Implement the artifact records operation for the component.

    Args:
        bundle: The bundle value used by the operation.

    Returns:
        The `tuple[Mapping[str, object], ...]` result produced by the operation.
    """
    records: list[Mapping[str, object]] = []
    for path in sorted(bundle.iterdir()):
        if not path.is_file() or path.name in {
            BUNDLE_MANIFEST_NAME,
            BUNDLE_LOCK_NAME,
            BUNDLE_SBOM_NAME,
            BUNDLE_SIGNATURE_NAME,
        }:
            continue
        if path.suffix != ".whl" and not path.name.endswith(".tar.gz"):
            continue
        records.append(artifact_record(path))
    return tuple(records)


def _record_key(record: Mapping[str, object]) -> tuple[object, ...]:
    """Record key.

    Args:
        record: The record value used by the operation.

    Returns:
        The `tuple[object, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_record_key`. It delegates to `get` while keeping
        intermediate state local to the owning operation.
    """
    return (
        record.get("filename"),
        record.get("bytes"),
        record.get("sha256"),
        record.get("distribution"),
        record.get("version"),
        record.get("kind"),
    )


def _validate_records(
    bundle: Path,
    records: Sequence[Mapping[str, object]],
    *,
    enforce_disk_set: bool,
) -> None:
    """Validate records.

    Args:
        bundle: The bundle value used by the operation.
        records: The records value used by the operation.
        enforce_disk_set: The enforce disk set value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_validate_records`. It delegates to `get`, `add`,
        `is_symlink`, `is_file` while keeping intermediate state local to the owning operation.
    """
    filenames: set[str] = set()
    for record in records:
        filename = record.get("filename")
        size = record.get("bytes")
        digest = record.get("sha256")
        distribution = record.get("distribution")
        version = record.get("version")
        kind = record.get("kind")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise BundleError("manifest artifact filename is invalid")
        if (
            not isinstance(size, int)
            or size < 0
            or not isinstance(digest, str)
            or len(digest) != 64
            or not isinstance(distribution, str)
            or not isinstance(version, str)
            or not isinstance(kind, str)
            or filename in filenames
        ):
            raise BundleError("dependency lock contains an invalid artifact record")
        filenames.add(filename)
        artifact = bundle / filename
        if (
            artifact.is_symlink()
            or not artifact.is_file()
            or artifact.stat().st_size != size
            or sha256_file(artifact) != digest
        ):
            raise BundleError(f"artifact integrity check failed for {filename}")
        if artifact_kind(artifact) != kind or artifact_metadata(artifact) != (distribution, version):
            raise BundleError(f"artifact metadata check failed for {filename}")
    if enforce_disk_set:
        disk_filenames = {record["filename"] for record in artifact_records(bundle)}
        if disk_filenames != filenames:
            raise BundleError("bundle contains an unregistered or missing package artifact")


def _verify_dependency_lock(
    bundle: Path,
    manifest: Mapping[str, object],
    records: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    """Verify dependency lock.

    Args:
        bundle: The bundle value used by the operation.
        manifest: Validated manifest describing the component contract.
        records: The records value used by the operation.

    Returns:
        The `Mapping[str, object]` result produced by the operation.

    Notes:
        Internal implementation detail for `_verify_dependency_lock`. It delegates to `get`,
        `is_symlink`, `is_file`, `stat` while keeping intermediate state local to the owning operation.
    """
    reference = manifest.get("dependency_lock")
    if not isinstance(reference, dict):
        raise BundleError("bundle manifest is missing its dependency lock reference")
    filename = reference.get("filename")
    size = reference.get("bytes")
    digest = reference.get("sha256")
    if filename != BUNDLE_LOCK_NAME or not isinstance(size, int) or not isinstance(digest, str):
        raise BundleError("bundle dependency lock reference is invalid")
    lock_path = bundle / BUNDLE_LOCK_NAME
    if (
        lock_path.is_symlink()
        or not lock_path.is_file()
        or lock_path.stat().st_size != size
        or sha256_file(lock_path) != digest
    ):
        raise BundleError("dependency lock integrity check failed")
    lock = read_canonical_json(lock_path)
    if lock.get("schema_version") != 1:
        raise BundleError("dependency lock schema is unsupported")
    lock_records = lock.get("artifacts")
    if not isinstance(lock_records, list) or not all(isinstance(record, dict) for record in lock_records):
        raise BundleError("dependency lock artifacts are invalid")
    normalized_lock = tuple(cast(Mapping[str, object], record) for record in lock_records)
    if {_record_key(record) for record in normalized_lock} != {_record_key(record) for record in records}:
        raise BundleError("dependency lock is not a complete bundle artifact closure")
    requirements = lock.get("requirements")
    if not isinstance(requirements, list) or not all(isinstance(item, str) and item.strip() for item in requirements):
        raise BundleError("dependency lock requirements are invalid")
    return lock


def _verify_sbom(bundle: Path, manifest: Mapping[str, object], records: Sequence[Mapping[str, object]]) -> None:
    """Verify sbom.

    Args:
        bundle: The bundle value used by the operation.
        manifest: Validated manifest describing the component contract.
        records: The records value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_verify_sbom`. It delegates to `read_canonical_json`, `get`,
        `all`, `cast` while keeping intermediate state local to the owning operation.
    """
    sbom = read_canonical_json(bundle / BUNDLE_SBOM_NAME)
    if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.5":
        raise BundleError("bundle SBOM is not CycloneDX 1.5")
    components = sbom.get("components")
    if not isinstance(components, list) or not all(isinstance(item, dict) for item in components):
        raise BundleError("bundle SBOM components are invalid")
    inventory = {
        (cast(dict[str, object], item).get("name"), cast(dict[str, object], item).get("version"))
        for item in components
    }
    expected = {(record.get("distribution"), record.get("version")) for record in records}
    manifest_components = manifest.get("components")
    if not isinstance(manifest_components, list):
        raise BundleError("bundle manifest components are invalid")
    expected.update(
        (cast(dict[str, object], item).get("distribution"), cast(dict[str, object], item).get("version"))
        for item in manifest_components
        if isinstance(item, dict)
    )
    if inventory != expected or len(components) != len(expected):
        raise BundleError("bundle SBOM inventory does not match the artifact closure")


def _verify_signature(
    signature: Path,
    manifest: Path,
    tag: str,
    *,
    command: str,
    verifier: SignatureVerifier | None,
) -> None:
    """Verify signature.

    Args:
        signature: The signature value used by the operation.
        manifest: Validated manifest describing the component contract.
        tag: The tag value used by the operation.
        command: Command or operation name to execute.
        verifier: The verifier value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_verify_signature`. It delegates to `verifier`, `run`,
        `split` while keeping intermediate state local to the owning operation.
    """
    if verifier is not None:
        verifier(signature, manifest, tag)
        return
    identity = f"https://github.com/LiteyukiStudio/LiteyukiBot/{BUNDLE_WORKFLOW_PATH}@refs/tags/{tag}"
    completed = subprocess.run(
        [
            *shlex.split(command),
            "verify",
            "identity",
            "--bundle",
            str(signature),
            "--cert-identity",
            identity,
            "--cert-oidc-issuer",
            BUNDLE_OIDC_ISSUER,
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise BundleError("Sigstore identity verification failed")


def verify_bundle(
    bundle: Path,
    *,
    tag: str = BUNDLE_TAG,
    sigstore_command: str = "sigstore",
    signature_verifier: SignatureVerifier | None = None,
) -> VerifiedBundle:
    """Verify a signed, complete, offline bundle before any profile mutation.

    Args:
        bundle: The bundle value used by the operation.
        tag: The tag value used by the operation.
        sigstore_command: The sigstore command value used by the operation.
        signature_verifier: The signature verifier value used by the operation.

    Returns:
        The `VerifiedBundle` result produced by the operation.
    """

    bundle = bundle.resolve()
    if tag != BUNDLE_TAG:
        raise BundleError(f"current Alpha9 tag must be {BUNDLE_TAG}")
    if not bundle.is_dir():
        raise BundleError(f"bundle directory does not exist: {bundle}")
    manifest_path = bundle / BUNDLE_MANIFEST_NAME
    signature_path = bundle / BUNDLE_SIGNATURE_NAME
    if not signature_path.is_file():
        raise BundleError("bundle is missing the Sigstore manifest bundle")
    manifest = read_canonical_json(manifest_path)
    if manifest.get("schema_version") != 1 or manifest.get("baseline") != dict(BUNDLE_BASELINE):
        raise BundleError("manifest schema or frozen Alpha8b baseline is invalid")
    if manifest.get("release") != {"tag": tag, "version": BUNDLE_VERSION}:
        raise BundleError("manifest release tag or version is invalid")
    components = manifest.get("components")
    if not isinstance(components, list) or not all(isinstance(item, dict) for item in components):
        raise BundleError("manifest components are invalid")
    component_ids = [cast(dict[str, object], item).get("id") for item in components]
    if len(component_ids) != len(set(component_ids)) or "devcli" not in component_ids:
        raise BundleError("manifest component inventory is invalid")
    for item in components:
        component = cast(dict[str, object], item)
        component_id = component.get("id")
        if not isinstance(component_id, str) or type(component.get("reserved")) is not bool:
            raise BundleError("manifest component flags are invalid")
        if component.get("reserved") is not (component_id == "devcli"):
            raise BundleError("manifest component reserved state is invalid")
    devcli = next(item for item in components if cast(dict[str, object], item).get("id") == "devcli")
    if devcli.get("distribution") != "liteyukibot-v7-devcli" or devcli.get("version") != BUNDLE_VERSION:
        raise BundleError("manifest DevCLI component is invalid")
    raw_records = manifest.get("artifacts")
    if not isinstance(raw_records, list) or not all(isinstance(item, dict) for item in raw_records):
        raise BundleError("manifest artifacts are invalid")
    records = tuple(cast(Mapping[str, object], item) for item in raw_records)
    _validate_records(bundle, records, enforce_disk_set=True)
    dependency_lock = _verify_dependency_lock(bundle, manifest, records)
    _verify_sbom(bundle, manifest, records)
    _verify_signature(
        signature_path,
        manifest_path,
        tag,
        command=sigstore_command,
        verifier=signature_verifier,
    )
    return VerifiedBundle(bundle, manifest, dependency_lock, records)


def requirements_from_lock(verified: VerifiedBundle) -> tuple[str, ...]:
    """Return exact install requirements, with a deterministic fixture fallback.

    Args:
        verified: The verified value used by the operation.

    Returns:
        The requested `tuple[str, ...]` value.
    """

    requirements = verified.requirements
    if requirements:
        return requirements
    selected: dict[str, str] = {}
    for record in verified.artifact_records:
        distribution = record.get("distribution")
        version = record.get("version")
        if isinstance(distribution, str) and isinstance(version, str):
            selected[distribution.lower().replace("_", "-")] = f"{distribution}=={version}"
    return tuple(selected[name] for name in sorted(selected))


__all__ = [
    "BUNDLE_BASELINE",
    "BUNDLE_LOCK_NAME",
    "BUNDLE_MANIFEST_NAME",
    "BUNDLE_SBOM_NAME",
    "BUNDLE_SIGNATURE_NAME",
    "BUNDLE_TAG",
    "BUNDLE_VERSION",
    "BundleError",
    "SignatureVerifier",
    "VerifiedBundle",
    "artifact_kind",
    "artifact_metadata",
    "artifact_record",
    "artifact_records",
    "canonical_json",
    "read_canonical_json",
    "requirements_from_lock",
    "sha256_file",
    "verify_bundle",
]
