from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Mapping
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
    def materialize(
        self, _artifacts: object, generation: Path, facets: Mapping[str, object]
    ) -> dict[str, object]:
        (generation / "payload").mkdir(exist_ok=True)
        return {"modules": sorted(facets), "directories": []}


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
    assert len(commands) == 3
    assert commands[1][-1] == "runtime-v6==1.2.3"
    assert commands[2][1] == "-c"
    assert commands[2][-2:] == ["runtime-v6", "host"]


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


def test_failed_generation_probe_keeps_the_previous_runtime_generation(
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
    first = service.install("example.root", runtime_id="legacy", runtime_kind="v6")

    def fail_probe(_path: Path, _runtime: RuntimePlugin) -> None:
        raise PluginStoreError("runtime generation health probe failed")

    monkeypatch.setattr(service, "_probe_generation", fail_probe)
    with pytest.raises(PluginStoreError, match="health probe failed"):
        service.install("example.second", runtime_id="legacy", runtime_kind="v6")

    store = RuntimeGenerationStore(tmp_path)
    assert store.active().runtime_generations == {"legacy": first.generation.id}
    assert store.active().previous == {}
    assert [generation.id for generation in store.list_generations("legacy")] == [first.generation.id]


def test_installer_rejects_managed_runtime_without_a_python_module_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, digest = _archive(tmp_path)
    monkeypatch.setattr(PluginSourceStore, "fetch", lambda _self, _source, refresh: _index(digest))
    monkeypatch.setattr(
        RuntimeCatalog,
        "discover",
        lambda _self: {
            "v6": RuntimePlugin("v6", ("runtime-host",), facet_installer=_Installer(), distribution="runtime-v6")
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

    with pytest.raises(PluginStoreError, match="must contain a Python -m module"):
        service.install("example.root", runtime_id="legacy", runtime_kind="v6")

    assert RuntimeGenerationStore(tmp_path).active().runtime_generations == {}


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
    commands: list[list[str]] = []

    def run(command: list[str]) -> None:
        commands.append(command)
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


def test_update_rebuilds_the_recorded_root_set_from_its_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, digest = _archive(tmp_path)
    index = _index(digest)
    fetches: list[str] = []

    def fetch(_self: object, source_id: str, refresh: bool) -> PluginIndex:
        assert refresh is True
        fetches.append(source_id)
        return index

    monkeypatch.setattr(PluginSourceStore, "fetch", fetch)
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
    updated = service.update(runtime_id="legacy", runtime_kind="v6")

    assert updated.generation.id != installed.generation.id
    assert updated.generation.roots == ("example.root",)
    assert fetches == ["liteyukibot-v7-plugins", "liteyukibot-v7-plugins"]


def test_disable_and_enable_rebuild_the_load_plan_without_fetching_sources(
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
    service.install("example.root", runtime_id="legacy", runtime_kind="v6")
    service.install("example.second", runtime_id="legacy", runtime_kind="v6")
    monkeypatch.setattr(PluginSourceStore, "fetch", lambda *_args, **_kwargs: pytest.fail("disable must not fetch"))

    disabled = service.disable("example.second", runtime_id="legacy", runtime_kind="v6")

    assert disabled.generation.disabled_roots == ("example.second",)
    assert disabled.generation.bundles == ("example.dependency", "example.root", "example.second")
    assert disabled.generation.load_plan["modules"] == ["example.dependency", "example.root"]
    assert any(command[:4] == ["uv", "pip", "install", "--offline"] for command in commands)
    enabled = service.enable("example.second", runtime_id="legacy", runtime_kind="v6")
    assert enabled.generation.disabled_roots == ()
    assert enabled.generation.load_plan["modules"] == ["example.dependency", "example.root", "example.second"]


def test_disable_and_uninstall_reject_a_root_required_by_another_root(
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
    service.install("example.dependency", runtime_id="legacy", runtime_kind="v6")
    service.install("example.root", runtime_id="legacy", runtime_kind="v6")

    with pytest.raises(PluginStoreError, match="required by enabled roots: example.root"):
        service.disable("example.dependency", runtime_id="legacy", runtime_kind="v6")
    with pytest.raises(PluginStoreError, match="required by roots: example.root"):
        service.uninstall("example.dependency", runtime_id="legacy", runtime_kind="v6")


def test_update_preserves_disabled_roots_while_refreshing_the_full_root_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, digest = _archive(tmp_path)
    index = _index(digest)
    fetches: list[str] = []

    def fetch(_self: object, source_id: str, refresh: bool) -> PluginIndex:
        assert refresh is True
        fetches.append(source_id)
        return index

    monkeypatch.setattr(PluginSourceStore, "fetch", fetch)
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
    service.disable("example.second", runtime_id="legacy", runtime_kind="v6")

    updated = service.update(runtime_id="legacy", runtime_kind="v6")

    assert updated.generation.roots == ("example.root", "example.second")
    assert updated.generation.disabled_roots == ("example.second",)
    assert updated.generation.load_plan["modules"] == ["example.dependency", "example.root"]
    assert fetches == ["liteyukibot-v7-plugins"] * 3


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


def test_plugin_rollback_cli_rejects_legacy_runtime_under_config_v5(
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

    assert main(["--workspace", str(tmp_path), "plugin", "rollback", "--runtime", "legacy"]) == 2
    assert "runtime 'legacy' is not configured" in capsys.readouterr().err
    assert store.active().runtime_generations == {"legacy": "second"}
