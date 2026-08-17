from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest
from scripts.alpha_release import (
    ALPHA_TAG,
    ALPHA_VERSION,
    LOCKSTEP_COMPONENTS,
    MANIFEST_NAME,
    SIGNATURE_NAME,
    AlphaReleaseError,
    create_manifest,
    create_sbom,
    validate_source_registry,
    verify_bundle,
)
from scripts.run_alpha_bundle_installs import VERIFICATIONS, command_for, wheels_for

ROOT = Path(__file__).resolve().parents[1]


def _metadata(distribution: str) -> bytes:
    return f"Metadata-Version: 2.3\nName: {distribution}\nVersion: {ALPHA_VERSION}\n".encode()


def _wheel(dist: Path, distribution: str) -> None:
    filename = f"{distribution.replace('-', '_')}-{ALPHA_VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(dist / filename, "w") as archive:
        archive.writestr(
            f"{distribution.replace('-', '_')}-{ALPHA_VERSION}.dist-info/METADATA", _metadata(distribution)
        )


def _sdist(dist: Path, distribution: str) -> None:
    filename = dist / f"{distribution}-{ALPHA_VERSION}.tar.gz"
    payload = _metadata(distribution)
    with tarfile.open(filename, "w:gz") as archive:
        info = tarfile.TarInfo(f"{distribution}-{ALPHA_VERSION}/PKG-INFO")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


def _bundle(tmp_path: Path) -> Path:
    dist = tmp_path / "bundle"
    dist.mkdir(parents=True)
    for component in LOCKSTEP_COMPONENTS:
        _wheel(dist, component.distribution)
        if component.requires_sdist:
            _sdist(dist, component.distribution)
    create_manifest(ROOT, dist)
    create_sbom(dist)
    (dist / SIGNATURE_NAME).write_text("{}", encoding="utf-8")
    return dist


def test_source_registry_matches_the_lockstep_alpha_one_metadata() -> None:
    validate_source_registry(ROOT)


def test_bundle_manifest_is_canonical_and_verifies_artifact_metadata(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    manifest = json.loads((bundle / MANIFEST_NAME).read_bytes())

    assert manifest["release"] == {"tag": ALPHA_TAG, "version": ALPHA_VERSION}
    assert manifest["baseline"] == {"broker": 6, "configuration": 5, "lyip": 2, "runtime_ipc": 6}
    assert manifest["components"][-1] == {
        "distribution": "liteyukibot-v7-devcli",
        "id": "devcli",
        "reserved": True,
        "version": ALPHA_VERSION,
    }
    assert b"\n" not in (bundle / MANIFEST_NAME).read_bytes()

    calls: list[tuple[Path, Path, str]] = []
    verify_bundle(
        bundle, signature_verifier=lambda signature, manifest_path, tag: calls.append((signature, manifest_path, tag))
    )

    assert calls == [(bundle / SIGNATURE_NAME, bundle / MANIFEST_NAME, ALPHA_TAG)]


def test_bundle_verifier_rejects_tampered_artifacts_and_wrong_tag(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    artifact = next(bundle.glob("*.whl"))
    artifact.write_bytes(b"tampered")

    with pytest.raises(AlphaReleaseError, match="integrity"):
        verify_bundle(bundle, signature_verifier=lambda _signature, _manifest, _tag: None)
    with pytest.raises(AlphaReleaseError, match="tag"):
        verify_bundle(bundle, tag="v7.0.0a2", signature_verifier=lambda _signature, _manifest, _tag: None)


def test_bundle_verifier_requires_signature_and_canonical_manifest(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    (bundle / SIGNATURE_NAME).unlink()
    with pytest.raises(AlphaReleaseError, match="Sigstore"):
        verify_bundle(bundle, signature_verifier=lambda _signature, _manifest, _tag: None)

    (bundle / SIGNATURE_NAME).write_text("{}", encoding="utf-8")
    (bundle / MANIFEST_NAME).write_text("{}\n", encoding="utf-8")
    with pytest.raises(AlphaReleaseError, match="canonical"):
        verify_bundle(bundle, signature_verifier=lambda _signature, _manifest, _tag: None)


def test_bundle_verifier_rejects_component_drift_and_path_escape(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    manifest_path = bundle / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_bytes())
    manifest["components"][-1]["reserved"] = False
    manifest_path.write_bytes(json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    with pytest.raises(AlphaReleaseError, match="reserved"):
        verify_bundle(bundle, signature_verifier=lambda _signature, _manifest, _tag: None)

    bundle = _bundle(tmp_path / "escaped")
    manifest_path = bundle / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_bytes())
    manifest["artifacts"][0]["filename"] = "../outside.whl"
    manifest_path.write_bytes(json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    with pytest.raises(AlphaReleaseError, match="filename"):
        verify_bundle(bundle, signature_verifier=lambda _signature, _manifest, _tag: None)


def test_bundle_install_commands_use_only_staged_wheels(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    command = command_for(bundle, VERIFICATIONS[1], "uv")

    assert command[:4] == ["uv", "run", "--no-project", "--python"]
    assert str(bundle / "liteyukibot_v7-7.0.0a1-py3-none-any.whl") in command
    assert str(bundle / "liteyukibot_v7_cordis-7.0.0a1-py3-none-any.whl") in command
    assert wheels_for(bundle, "liteyukibot-v7-webui") == (bundle / "liteyukibot_v7_webui-7.0.0a1-py3-none-any.whl",)
