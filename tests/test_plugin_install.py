from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from liteyukibot.cli import main
from liteyukibot.config import ConfigWorkspace
from liteyukibot.plugin_install import PluginInstallationService
from liteyukibot.plugin_sources import PluginSourceStore
from liteyukibot.plugin_store import (
    PlatformTarget,
    PluginIndex,
    PluginStoreError,
    RuntimeGeneration,
    RuntimeGenerationStore,
)
from liteyukibot.runtime import RuntimeCatalog, RuntimePlugin


class _Installer:
    def materialize(self, _artifacts: object, generation: Path, _facets: object) -> dict[str, object]:
        (generation / "payload").mkdir(exist_ok=True)
        return {"modules": ["example_plugin"], "directories": []}


def _index(digest: str, *, wheel_digest: str | None = None, dependency_cycle: bool = False) -> PluginIndex:
    dependencies = ["example.dependency"] if not dependency_cycle else ["example.root"]
    return PluginIndex.parse(
        {
            "schema": 1,
            "bundles": [
                {
                    "id": "example.root",
                    "version": "1.0.0",
                    "dependencies": dependencies,
                    "facets": [
                        {
                            "runtime_kind": "v6",
                            "artifacts": [{"url": "https://example.invalid/root.zip", "sha256": digest}],
                            "wheels": (
                                [{"url": "https://example.invalid/dependency.whl", "sha256": wheel_digest}]
                                if wheel_digest is not None
                                else []
                            ),
                            "load": {"modules": ["example_root"]},
                        }
                    ],
                },
                {
                    "id": "example.dependency",
                    "version": "1.0.0",
                    "dependencies": [],
                    "facets": [
                        {
                            "runtime_kind": "v6",
                            "artifacts": [{"url": "https://example.invalid/dependency.zip", "sha256": digest}],
                            "load": {"modules": ["example_dependency"]},
                        }
                    ],
                },
                {
                    "id": "example.second",
                    "version": "1.0.0",
                    "dependencies": [],
                    "facets": [
                        {
                            "runtime_kind": "v6",
                            "artifacts": [{"url": "https://example.invalid/second.zip", "sha256": digest}],
                            "load": {"modules": ["example_second"]},
                        }
                    ],
                },
            ],
        }
    )


def _archive(tmp_path: Path) -> tuple[Path, str]:
    archive = tmp_path / "plugin.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("plugin.py", "VALUE = 1\n")
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def _wheel(tmp_path: Path) -> tuple[Path, str]:
    wheel = tmp_path / "dependency.whl"
    with zipfile.ZipFile(wheel, "w") as value:
        value.writestr("dependency-1.0.0.dist-info/METADATA", "Name: dependency\nVersion: 1.0.0\n")
        value.writestr("dependency-1.0.0.dist-info/WHEEL", "Wheel-Version: 1.0\nTag: py3-none-any\n")
    return wheel, hashlib.sha256(wheel.read_bytes()).hexdigest()


def test_installer_resolves_dependencies_and_activates_only_after_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, digest = _archive(tmp_path)
    index = _index(digest)
    monkeypatch.setattr(PluginSourceStore, "fetch", lambda _self, _source, refresh: index)
    monkeypatch.setattr(
        RuntimeCatalog,
        "discover",
        lambda _self: {
            "v6": RuntimePlugin(
                "v6", ("python", "-m", "host"), facet_installer=_Installer(), distribution="runtime-v6"
            )
        },
    )
    monkeypatch.setattr("liteyukibot.plugin_install.metadata.version", lambda _distribution: "1.2.3")

    commands: list[list[str]] = []

    def run(command: list[str]) -> None:
        commands.append(command)
        if command[1] == "venv":
            python = Path(command[-1]) / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")

    service = PluginInstallationService(tmp_path, run=run)
    monkeypatch.setattr(service.artifacts, "fetch", lambda _artifact: service.artifacts.import_file(archive, digest))
    result = service.install("example.root", runtime_id="legacy", runtime_kind="v6")

    active = RuntimeGenerationStore(tmp_path).active()
    assert active.runtime_generations == {"legacy": result.generation.id}
    assert result.generation.bundles == ("example.dependency", "example.root")
    assert result.generation.roots == ("example.root",)
    assert result.generation.source_id == "liteyukibot-v7-plugins"
    assert result.generation.resolved_bundles[-1].id == "example.root"
    assert len(commands) == 2
    assert commands[1][-1] == "runtime-v6==1.2.3"


def test_installer_stages_hash_verified_wheels_without_index_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, digest = _archive(tmp_path)
    wheel, wheel_digest = _wheel(tmp_path)
    index = _index(digest, wheel_digest=wheel_digest)
    monkeypatch.setattr(PluginSourceStore, "fetch", lambda _self, _source, refresh: index)
    monkeypatch.setattr(
        RuntimeCatalog,
        "discover",
        lambda _self: {
            "v6": RuntimePlugin(
                "v6", ("python", "-m", "host"), facet_installer=_Installer(), distribution="runtime-v6"
            )
        },
    )
    monkeypatch.setattr("liteyukibot.plugin_install.metadata.version", lambda _distribution: "1.2.3")
    commands: list[list[str]] = []

    def run(command: list[str]) -> None:
        commands.append(command)
        if command[1] == "venv":
            python = Path(command[-1]) / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")

    service = PluginInstallationService(tmp_path, run=run)
    sources = {digest: archive, wheel_digest: wheel}
    monkeypatch.setattr(
        service.artifacts,
        "fetch",
        lambda artifact: service.artifacts.import_file(sources[artifact.sha256], artifact.sha256),
    )
    result = service.install("example.root", runtime_id="legacy", runtime_kind="v6")

    assert commands[2][:6] == ["uv", "pip", "install", "--no-index", "--no-deps", "--python"]
    assert Path(commands[2][-1]).parent.name == "wheels"
    assert Path(commands[2][-1]).name == f"{wheel_digest}.whl"
    assert Path(commands[2][-1]).is_file()
    assert wheel_digest in result.generation.artifacts


def test_installer_rejects_dependency_cycles_before_creating_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, digest = _archive(tmp_path)
    monkeypatch.setattr(
        PluginSourceStore,
        "fetch",
        lambda _self, _source, refresh: _index(digest, dependency_cycle=True),
    )
    service = PluginInstallationService(tmp_path)

    with pytest.raises(PluginStoreError, match="cycle"):
        service.install("example.root", runtime_id="legacy", runtime_kind="v6")

    assert not (tmp_path / ".liteyuki" / "plugins" / "runtimes").exists()


def test_failed_environment_creation_does_not_activate_or_retain_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, digest = _archive(tmp_path)
    monkeypatch.setattr(PluginSourceStore, "fetch", lambda _self, _source, refresh: _index(digest))
    monkeypatch.setattr(
        RuntimeCatalog,
        "discover",
        lambda _self: {
            "v6": RuntimePlugin(
                "v6", ("python", "-m", "host"), facet_installer=_Installer(), distribution="runtime-v6"
            )
        },
    )
    monkeypatch.setattr("liteyukibot.plugin_install.metadata.version", lambda _distribution: "1.2.3")

    def fail(_command: list[str]) -> None:
        raise PluginStoreError("command failed")

    service = PluginInstallationService(tmp_path, run=fail)
    monkeypatch.setattr(service.artifacts, "fetch", lambda _artifact: service.artifacts.import_file(archive, digest))
    with pytest.raises(PluginStoreError, match="command failed"):
        service.install("example.root", runtime_id="legacy", runtime_kind="v6")

    store = RuntimeGenerationStore(tmp_path)
    assert store.active().runtime_generations == {}
    assert not (tmp_path / ".liteyuki" / "plugins" / "runtimes" / "legacy" / "generations").exists()


def test_installer_adds_a_root_without_dropping_the_active_generation_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, digest = _archive(tmp_path)
    index = _index(digest)
    monkeypatch.setattr(PluginSourceStore, "fetch", lambda _self, _source, refresh: index)
    monkeypatch.setattr(
        RuntimeCatalog,
        "discover",
        lambda _self: {
            "v6": RuntimePlugin(
                "v6", ("python", "-m", "host"), facet_installer=_Installer(), distribution="runtime-v6"
            )
        },
    )
    monkeypatch.setattr("liteyukibot.plugin_install.metadata.version", lambda _distribution: "1.2.3")

    def run(command: list[str]) -> None:
        if command[1] == "venv":
            python = Path(command[-1]) / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")

    service = PluginInstallationService(tmp_path, run=run)
    monkeypatch.setattr(service.artifacts, "fetch", lambda _artifact: service.artifacts.import_file(archive, digest))
    service.install("example.root", runtime_id="legacy", runtime_kind="v6")
    result = service.install("example.second", runtime_id="legacy", runtime_kind="v6")

    assert result.generation.roots == ("example.root", "example.second")
    assert result.generation.bundles == ("example.dependency", "example.root", "example.second")
    restored = RuntimeGenerationStore(tmp_path).read("legacy", result.generation.id)
    assert restored.resolved_bundles == result.generation.resolved_bundles


def test_uninstall_rebuilds_remaining_roots_from_the_generation_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, digest = _archive(tmp_path)
    index = _index(digest)
    monkeypatch.setattr(PluginSourceStore, "fetch", lambda _self, _source, refresh: index)
    monkeypatch.setattr(
        RuntimeCatalog,
        "discover",
        lambda _self: {
            "v6": RuntimePlugin(
                "v6", ("python", "-m", "host"), facet_installer=_Installer(), distribution="runtime-v6"
            )
        },
    )
    monkeypatch.setattr("liteyukibot.plugin_install.metadata.version", lambda _distribution: "1.2.3")

    def run(command: list[str]) -> None:
        if command[1] == "venv":
            python = Path(command[-1]) / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")

    service = PluginInstallationService(tmp_path, run=run)
    monkeypatch.setattr(service.artifacts, "fetch", lambda _artifact: service.artifacts.import_file(archive, digest))
    service.install("example.root", runtime_id="legacy", runtime_kind="v6")
    service.install("example.second", runtime_id="legacy", runtime_kind="v6")
    monkeypatch.setattr(
        PluginSourceStore,
        "fetch",
        lambda *_args, **_kwargs: pytest.fail("uninstall must not fetch an index"),
    )

    result = service.uninstall("example.second", runtime_id="legacy", runtime_kind="v6")

    assert result.generation is not None
    assert result.generation.roots == ("example.root",)
    assert result.generation.bundles == ("example.dependency", "example.root")


def test_uninstalling_the_final_root_deactivates_but_keeps_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, digest = _archive(tmp_path)
    index = _index(digest)
    monkeypatch.setattr(PluginSourceStore, "fetch", lambda _self, _source, refresh: index)
    monkeypatch.setattr(
        RuntimeCatalog,
        "discover",
        lambda _self: {
            "v6": RuntimePlugin(
                "v6", ("python", "-m", "host"), facet_installer=_Installer(), distribution="runtime-v6"
            )
        },
    )
    monkeypatch.setattr("liteyukibot.plugin_install.metadata.version", lambda _distribution: "1.2.3")

    def run(command: list[str]) -> None:
        if command[1] == "venv":
            python = Path(command[-1]) / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")

    service = PluginInstallationService(tmp_path, run=run)
    monkeypatch.setattr(service.artifacts, "fetch", lambda _artifact: service.artifacts.import_file(archive, digest))
    installed = service.install("example.root", runtime_id="legacy", runtime_kind="v6")

    assert service.uninstall("example.root", runtime_id="legacy", runtime_kind="v6").generation is None
    store = RuntimeGenerationStore(tmp_path)
    assert store.active().runtime_generations == {}
    assert store.rollback("legacy").runtime_generations == {"legacy": installed.generation.id}


def test_plugin_rollback_cli_switches_to_the_previous_generation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ConfigWorkspace(tmp_path).initialize(runtimes={"legacy": {"kind": "v6"}})
    store = RuntimeGenerationStore(tmp_path)
    first = RuntimeGeneration(
        "first",
        "legacy",
        "v6",
        "2026-08-11T00:00:00+00:00",
        PlatformTarget("windows", "amd64", "3.14"),
        ("example.first",),
        ("a" * 64,),
        {"modules": [], "directories": []},
    )
    second = RuntimeGeneration(
        "second",
        "legacy",
        "v6",
        "2026-08-11T00:00:01+00:00",
        PlatformTarget("windows", "amd64", "3.14"),
        ("example.second",),
        ("b" * 64,),
        {"modules": [], "directories": []},
    )
    store.write(first)
    store.write(second)
    store.activate("legacy", first.id)
    store.activate("legacy", second.id)

    assert main(["--workspace", str(tmp_path), "plugin", "rollback", "--runtime", "legacy"]) == 0

    assert store.active().runtime_generations == {"legacy": "first"}
    assert capsys.readouterr().out.strip() == "activated first"
