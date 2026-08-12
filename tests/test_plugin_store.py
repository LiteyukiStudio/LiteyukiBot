from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from liteyukibot.plugin_store import (
    ArtifactSpec,
    ArtifactStore,
    PlatformConstraint,
    PlatformTarget,
    PluginIndex,
    PluginStoreError,
    RuntimeGeneration,
    RuntimeGenerationStore,
)


def _index() -> dict[str, object]:
    digest = "a" * 64
    return {
        "schema": 1,
        "bundles": [
            {
                "id": "example.echo",
                "version": "1.0.0",
                "dependencies": [],
                "facets": [
                    {
                        "runtime_kind": "v6",
                        "artifacts": [{"url": "https://example.invalid/echo.zip", "sha256": digest}],
                        "requirements": ["requests>=2"],
                        "platform": {"systems": ["windows"], "machines": ["amd64"], "pythons": ["3.14"]},
                        "load": {"modules": ["example_echo"]},
                        "capabilities": ["runtime.events.receive"],
                    }
                ],
            }
        ],
    }


def test_index_has_deterministic_digest_and_targeted_facets() -> None:
    index = PluginIndex.parse(_index())

    bundle = index.require("example.echo")
    facet = bundle.facet_for("v6", PlatformTarget("Windows", "AMD64", "3.14"))

    assert facet.load == {"modules": ["example_echo"]}
    assert index.digest == PluginIndex.parse(json.loads(json.dumps(_index()))).digest
    with pytest.raises(PluginStoreError, match="compatible"):
        bundle.facet_for("v6", PlatformTarget("Linux", "x86_64", "3.14"))


def test_platform_constraint_matches_only_the_declared_target() -> None:
    constraint = PlatformConstraint(("windows",), ("amd64",), ("3.14",))

    assert constraint.matches(PlatformTarget("windows", "amd64", "3.14"))
    assert not constraint.matches(PlatformTarget("windows", "arm64", "3.14"))


def test_artifact_store_hashes_and_extracts_safe_zip(tmp_path: Path) -> None:
    archive = tmp_path / "plugin.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("example/plugin.py", "VALUE = 1\n")
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    store = ArtifactStore(tmp_path)

    stored = store.import_file(archive, expected)
    extracted = store.extract_zip(expected, tmp_path / "generation" / "payload")

    assert stored.read_bytes() == archive.read_bytes()
    assert (extracted / "example" / "plugin.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_artifact_store_rejects_zip_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("../escape.py", "VALUE = 1\n")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    store = ArtifactStore(tmp_path)
    store.import_file(archive, digest)

    with pytest.raises(PluginStoreError, match="unsafe path"):
        store.extract_zip(digest, tmp_path / "generation" / "payload")


def test_artifact_store_rejects_https_downgrade_redirect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response(io.BytesIO):
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> None:
            self.close()

        def geturl(self) -> str:
            return "http://example.invalid/plugin.zip"

    digest = "a" * 64
    monkeypatch.setattr("liteyukibot.plugin_store.urlopen", lambda *_args, **_kwargs: _Response(b"payload"))

    with pytest.raises(PluginStoreError, match="redirect"):
        ArtifactStore(tmp_path).fetch(ArtifactSpec("https://example.invalid/plugin.zip", digest))


def _generation(generation_id: str) -> RuntimeGeneration:
    return RuntimeGeneration(
        generation_id,
        "legacy",
        "v6",
        "2026-08-11T00:00:00+00:00",
        PlatformTarget("windows", "amd64", "3.14"),
        ("example.echo",),
        ("b" * 64,),
        {"modules": ["example_echo"]},
    )


def test_runtime_generation_activation_and_rollback_share_one_lock(tmp_path: Path) -> None:
    store = RuntimeGenerationStore(tmp_path)
    first = _generation("first")
    second = _generation("second")
    store.write(first)
    store.write(second)

    store.activate("legacy", first.id)
    activated = store.activate("legacy", second.id)
    rolled_back = store.rollback("legacy")

    assert activated.runtime_generations == {"legacy": "second"}
    assert activated.previous == {"legacy": "first"}
    assert rolled_back.runtime_generations == {"legacy": "first"}
    assert rolled_back.previous == {"legacy": "second"}
    assert json.loads((tmp_path / "liteyuki.lock").read_text(encoding="utf-8"))["schema"] == 2
