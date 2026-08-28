from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from scripts.alpha_release import (
    ALPHA_TAG,
    ALPHA_VERSION,
    MANIFEST_NAME,
    RELEASE_COMPONENTS,
    SIGNATURE_NAME,
    AlphaReleaseError,
    create_manifest,
    create_sbom,
    validate_source_registry,
    verify_bundle,
)
from scripts.release_registry import resolve_workspace_registry
from scripts.run_alpha_bundle_installs import VERIFICATIONS, command_for, wheels_for

ROOT = Path(__file__).resolve().parents[1]
TARGET_DISTRIBUTIONS = {
    "liteyukibot-v7",
    "liteyukibot-v7-kernel",
    "liteyukibot-v7-cordis",
    "liteyukibot-v7-adapter-onebot",
}


def _metadata(distribution: str, version: str) -> bytes:
    return f"Metadata-Version: 2.3\nName: {distribution}\nVersion: {version}\n".encode()


def _wheel(dist: Path, distribution: str, version: str) -> None:
    filename = f"{distribution.replace('-', '_')}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(dist / filename, "w") as archive:
        archive.writestr(
            f"{distribution.replace('-', '_')}-{version}.dist-info/METADATA", _metadata(distribution, version)
        )


def _sdist(dist: Path, distribution: str, version: str) -> None:
    filename = dist / f"{distribution}-{version}.tar.gz"
    payload = _metadata(distribution, version)
    with tarfile.open(filename, "w:gz") as archive:
        info = tarfile.TarInfo(f"{distribution}-{version}/PKG-INFO")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


def _bundle(tmp_path: Path) -> Path:
    dist = tmp_path / "bundle"
    dist.mkdir(parents=True)
    for component in RELEASE_COMPONENTS:
        _wheel(dist, component.distribution, component.release_version)
        if component.requires_sdist:
            _sdist(dist, component.distribution, component.release_version)
    create_manifest(ROOT, dist)
    create_sbom(dist)
    (dist / SIGNATURE_NAME).write_text("{}", encoding="utf-8")
    return dist


def test_source_registry_matches_alpha15_target() -> None:
    validate_source_registry(ROOT)
    registry = resolve_workspace_registry(ROOT)
    assert {component.distribution for component in registry.components} == TARGET_DISTRIBUTIONS
    assert {component.version for component in registry.components} == {"7.0.0a15"}


def test_alpha_release_script_supports_direct_execution() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "alpha_release.py"), "check-source"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_bundle_manifest_is_canonical_and_verifies_four_artifacts(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    manifest = json.loads((bundle / MANIFEST_NAME).read_bytes())

    assert manifest["release"] == {"tag": ALPHA_TAG, "version": ALPHA_VERSION}
    assert manifest["baseline"] == {"configuration": 7}
    assert {component["id"] for component in manifest["components"]} == {
        "kernel",
        "root",
        "cordis",
        "adapter-onebot",
    }
    assert {component["distribution"] for component in manifest["components"]} == TARGET_DISTRIBUTIONS
    assert all(component["reserved"] is False for component in manifest["components"])
    assert manifest["dependency_lock"]["filename"] == "dependencies.lock.json"
    assert b"\n" not in (bundle / MANIFEST_NAME).read_bytes()

    calls: list[tuple[Path, Path, str]] = []
    verify_bundle(
        bundle, signature_verifier=lambda signature, manifest_path, tag: calls.append((signature, manifest_path, tag))
    )

    assert calls == [(bundle / SIGNATURE_NAME, bundle / MANIFEST_NAME, ALPHA_TAG)]


def test_bundle_verifier_rejects_a_missing_target_component(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    manifest_path = bundle / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_bytes())
    manifest["components"] = [item for item in manifest["components"] if item["id"] != "cordis"]
    manifest_path.write_bytes(json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode())

    with pytest.raises(AlphaReleaseError, match="component inventory"):
        verify_bundle(bundle, signature_verifier=lambda _signature, _manifest, _tag: None)


def test_bundle_verifier_rejects_tampered_artifacts_and_wrong_tag(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    next(bundle.glob("*.whl")).write_bytes(b"tampered")

    with pytest.raises(AlphaReleaseError, match="integrity"):
        verify_bundle(bundle, signature_verifier=lambda _signature, _manifest, _tag: None)
    with pytest.raises(AlphaReleaseError, match="tag"):
        verify_bundle(bundle, tag="v7.0.0a14", signature_verifier=lambda _signature, _manifest, _tag: None)


def test_bundle_verifier_requires_signature_and_canonical_manifest(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    (bundle / SIGNATURE_NAME).unlink()
    with pytest.raises(AlphaReleaseError, match="Sigstore"):
        verify_bundle(bundle, signature_verifier=lambda _signature, _manifest, _tag: None)

    (bundle / SIGNATURE_NAME).write_text("{}", encoding="utf-8")
    (bundle / MANIFEST_NAME).write_text("{}\n", encoding="utf-8")
    with pytest.raises(AlphaReleaseError, match="canonical"):
        verify_bundle(bundle, signature_verifier=lambda _signature, _manifest, _tag: None)


def test_bundle_install_commands_use_only_staged_target_wheels(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    command = command_for(bundle, next(item for item in VERIFICATIONS if item.name == "cordis"), "uv")

    assert command[:4] == ["uv", "run", "--no-project", "--python"]
    assert str(bundle / f"liteyukibot_v7_kernel-{ALPHA_VERSION}-py3-none-any.whl") in command
    assert str(bundle / f"liteyukibot_v7_cordis-{ALPHA_VERSION}-py3-none-any.whl") in command
    with pytest.raises(AlphaReleaseError, match="missing a wheel"):
        wheels_for(bundle, "liteyukibot-v7-webui")


def test_bundle_verifier_projection_covers_exactly_four_components() -> None:
    assert len(VERIFICATIONS) == 4
    assert {verification.name for verification in VERIFICATIONS} == {
        "kernel",
        "root",
        "cordis",
        "adapter-onebot",
    }
    adapter = next(item for item in VERIFICATIONS if item.name == "adapter-onebot")
    assert adapter.distributions == ("liteyukibot-v7-kernel", "liteyukibot-v7-adapter-onebot")
    assert adapter.arguments == ("--expected-version", ALPHA_VERSION)
    root = next(item for item in VERIFICATIONS if item.name == "root")
    assert root.distributions == (
        "liteyukibot-v7-kernel",
        "liteyukibot-v7-cordis",
        "liteyukibot-v7-adapter-onebot",
        "liteyukibot-v7",
    )
