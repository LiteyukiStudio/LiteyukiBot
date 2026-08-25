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
    MANIFEST_NAME,
    RELEASE_COMPONENTS,
    SIGNATURE_NAME,
    AlphaReleaseError,
    create_manifest,
    create_sbom,
    validate_source_registry,
    verify_bundle,
)
from scripts.check_release import RELEASE_PROJECTS
from scripts.release_registry import ReleaseRegistryError, resolve_workspace_registry, validate_first_party_pins
from scripts.run_alpha_bundle_installs import VERIFICATIONS, command_for, wheels_for

ROOT = Path(__file__).resolve().parents[1]
RETIRED_BRIDGE_DISTRIBUTIONS = {
    "liteyukibot-v7-runtime-astrbot",
    "liteyukibot-v7-runtime-astrbot-api",
    "liteyukibot-v7-runtime-mofox",
    "liteyukibot-v7-runtime-v6",
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


def test_source_registry_matches_the_lockstep_alpha_one_metadata() -> None:
    validate_source_registry(ROOT)


def test_release_registry_covers_exactly_the_workspace_bundle() -> None:
    registry = resolve_workspace_registry(ROOT)
    distributions = {component.distribution for component in registry.components}

    assert len(registry.components) == 19
    assert {
        "liteyukibot-v7",
        "liteyukibot-v7-ipc-native",
        "liteyukibot-v7-cordis",
        "liteyukibot-v7-runtime-nonebot",
        "liteyukibot-v7-runtime-nonebot-api",
        "liteyukibot-v7-runtime-adapter",
        "liteyukibot-v7-adapter-onebot",
        "liteyukibot-v7-adapter-satori",
        "liteyukibot-v7-webui",
        "liteyukibot-v7-example-nonebot-plugin",
        "liteyukibot-v7-permissions",
        "liteyukibot-v7-commands",
        "liteyukibot-v7-resources",
        "liteyukibot-v7-profile",
        "liteyukibot-v7-essentials",
        "liteyukibot-v7-agent-resolver",
        "liteyukibot-v7-agent",
        "liteyukibot-v7-functions",
        "liteyukibot-v7-devcli",
    } == distributions
    assert all(not component.project_dir.startswith("extras/") for component in registry.components)
    assert "examples/native-plugin" not in {component.project_dir for component in registry.components}
    assert "examples/broker-peer" not in {component.project_dir for component in registry.components}
    assert {component.component_id for component in registry.components if component.policy.tag_prefix is None} == {
        "cordis",
        "nonebot-api",
        "example-nonebot-plugin",
        "devcli",
    }
    reference = registry.reference_e2e_component
    assert reference.component_id == "example-nonebot-plugin"
    assert reference.policy.reference_e2e_components == ("kernel", "nonebot-bridge", "example-nonebot-plugin")


def test_publishable_projection_preserves_release_cli_names() -> None:
    assert set(RELEASE_PROJECTS) == {
        "root",
        "ipc-native",
        "runtime-nonebot",
        "runtime-adapter",
        "adapter-onebot",
        "adapter-satori",
        "webui",
        "permissions",
        "commands",
        "resources",
        "profile",
        "essentials",
        "agent-resolver",
        "agent",
        "functions",
    }


def test_release_registry_requires_exact_required_and_optional_first_party_pins() -> None:
    registry = resolve_workspace_registry(ROOT)
    validate_first_party_pins(registry)


def test_release_registry_rejects_a_broad_optional_first_party_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = resolve_workspace_registry(ROOT)
    from scripts import release_registry

    original = release_registry._read_project

    def read_project(project_file: Path) -> dict[str, object]:
        project = original(project_file)
        if project_file.parent.name == "permissions":
            project["optional-dependencies"] = {"cordis": ["liteyukibot-v7-cordis>=7.0.0a1,<8"]}
        return project

    monkeypatch.setattr(release_registry, "_read_project", read_project)
    with pytest.raises(ReleaseRegistryError, match="liteyukibot-v7-cordis"):
        validate_first_party_pins(registry)


def test_release_registry_rejects_lockstep_metadata_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import release_registry

    original = release_registry._read_project

    def read_project(project_file: Path) -> dict[str, object]:
        project = original(project_file)
        if project_file.parent.name == "cordis":
            project["version"] = "7.0.0a13"
        return project

    monkeypatch.setattr(release_registry, "_read_project", read_project)
    with pytest.raises(ReleaseRegistryError, match="lockstep version"):
        resolve_workspace_registry(ROOT)


def test_legacy_bridge_snapshots_are_excluded_from_mainline_release() -> None:
    active_distributions = {component.distribution for component in RELEASE_COMPONENTS}
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert RETIRED_BRIDGE_DISTRIBUTIONS.isdisjoint(active_distributions)
    for distribution in RETIRED_BRIDGE_DISTRIBUTIONS:
        assert f'name = "{distribution}"' not in lock
    for project in ("runtime-astrbot", "runtime-astrbot-api", "runtime-mofox", "runtime-v6"):
        assert not (ROOT / "packages" / project).exists()
        assert (ROOT / "extras" / "legacy-bridges" / project / "pyproject.toml").is_file()


def test_bundle_manifest_is_canonical_and_verifies_artifact_metadata(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    manifest = json.loads((bundle / MANIFEST_NAME).read_bytes())

    assert manifest["release"] == {"tag": ALPHA_TAG, "version": ALPHA_VERSION}
    assert manifest["baseline"] == {"broker": 7, "configuration": 6, "lyip": 2, "runtime_ipc": 7}
    assert manifest["components"][-1]["distribution"] == "liteyukibot-v7-devcli"
    assert manifest["components"][-1]["id"] == "devcli"
    assert manifest["components"][-1]["reserved"] is True
    assert manifest["components"][-1]["version"] == ALPHA_VERSION
    assert any(
        component["id"] == "example-nonebot-plugin"
        and component["distribution"] == "liteyukibot-v7-example-nonebot-plugin"
        and component["version"] == "0.1.0"
        for component in manifest["components"]
    )
    assert manifest["dependency_lock"]["filename"] == "dependencies.lock.json"
    assert b"\n" not in (bundle / MANIFEST_NAME).read_bytes()

    calls: list[tuple[Path, Path, str]] = []
    verify_bundle(
        bundle, signature_verifier=lambda signature, manifest_path, tag: calls.append((signature, manifest_path, tag))
    )

    assert calls == [(bundle / SIGNATURE_NAME, bundle / MANIFEST_NAME, ALPHA_TAG)]


def test_bundle_verifier_rejects_a_missing_workspace_component(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    manifest_path = bundle / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_bytes())
    manifest["components"] = [item for item in manifest["components"] if item["id"] != "agent"]
    manifest_path.write_bytes(json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode("utf-8"))

    with pytest.raises(AlphaReleaseError, match="component inventory"):
        verify_bundle(bundle, signature_verifier=lambda _signature, _manifest, _tag: None)


@pytest.mark.parametrize("mutation", ["unknown", "duplicate"])
def test_bundle_verifier_rejects_unknown_or_duplicate_component(tmp_path: Path, mutation: str) -> None:
    bundle = _bundle(tmp_path / mutation)
    manifest_path = bundle / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_bytes())
    if mutation == "unknown":
        manifest["components"].append(
            {
                "id": "unknown",
                "distribution": "liteyukibot-v7-unknown",
                "version": ALPHA_VERSION,
                "license": "LicenseRef-LSO-Common-1.4",
                "reserved": False,
                "independent": False,
            }
        )
    else:
        manifest["components"].append(dict(next(item for item in manifest["components"] if item["id"] == "agent")))
    manifest_path.write_bytes(json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode("utf-8"))

    with pytest.raises(AlphaReleaseError, match="inventory"):
        verify_bundle(bundle, signature_verifier=lambda _signature, _manifest, _tag: None)


def test_bundle_verifier_rejects_tampered_artifacts_and_wrong_tag(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    artifact = next(bundle.glob("*.whl"))
    artifact.write_bytes(b"tampered")

    with pytest.raises(AlphaReleaseError, match="integrity"):
        verify_bundle(bundle, signature_verifier=lambda _signature, _manifest, _tag: None)
    with pytest.raises(AlphaReleaseError, match="tag"):
        verify_bundle(bundle, tag="v7.0.0a7", signature_verifier=lambda _signature, _manifest, _tag: None)


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
    command = command_for(bundle, next(item for item in VERIFICATIONS if item.name == "cordis"), "uv")

    assert command[:4] == ["uv", "run", "--no-project", "--python"]
    assert str(bundle / f"liteyukibot_v7-{ALPHA_VERSION}-py3-none-any.whl") in command
    assert str(bundle / f"liteyukibot_v7_cordis-{ALPHA_VERSION}-py3-none-any.whl") in command
    assert wheels_for(bundle, "liteyukibot-v7-webui") == (
        bundle / f"liteyukibot_v7_webui-{ALPHA_VERSION}-py3-none-any.whl",
    )


def test_bundle_verifier_projection_covers_every_non_reference_component() -> None:
    names = {verification.name for verification in VERIFICATIONS}
    assert len(VERIFICATIONS) == 18
    assert "example-nonebot-plugin" not in names
    assert names == {
        component.component_id for component in RELEASE_COMPONENTS if component.component_id != "example-nonebot-plugin"
    }

    onebot = next(item for item in VERIFICATIONS if item.name == "adapter-onebot")
    assert onebot.distributions == (
        "liteyukibot-v7",
        "liteyukibot-v7-runtime-adapter",
        "liteyukibot-v7-adapter-onebot",
    )
    assert onebot.arguments == ("--expected-version", "0.1.0a1")

    satori = next(item for item in VERIFICATIONS if item.name == "adapter-satori")
    assert satori.distributions == (
        "liteyukibot-v7",
        "liteyukibot-v7-runtime-adapter",
        "liteyukibot-v7-adapter-satori",
    )
    assert satori.arguments == ("--expected-version", "0.1.0a2")

    agent = next(item for item in VERIFICATIONS if item.name == "agent")
    assert agent.distributions == (
        "liteyukibot-v7",
        "liteyukibot-v7-permissions",
        "liteyukibot-v7-commands",
        "liteyukibot-v7-agent-resolver",
        "liteyukibot-v7-agent",
    )
    assert agent.arguments == ("--expected-version", "0.1.0a9")
