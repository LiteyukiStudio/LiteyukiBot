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
                        "wheels": [],
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


def test_index_rejects_unpinned_requirements_in_favor_of_wheels() -> None:
    document = json.loads(json.dumps(_index()))
    facet = document["bundles"][0]["facets"][0]
    facet["requirements"] = ["requests>=2"]

    with pytest.raises(PluginStoreError, match="hash-verified wheels"):
        PluginIndex.parse(document)


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


def test_artifact_store_rejects_too_many_zip_members(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "many.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("first.txt", "1")
        value.writestr("second.txt", "2")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    store = ArtifactStore(tmp_path)
    store.import_file(archive, digest)
    monkeypatch.setattr("liteyukibot.plugin_store._MAX_ARCHIVE_MEMBERS", 1)

    with pytest.raises(PluginStoreError, match="too many members"):
        store.extract_zip(digest, tmp_path / "generation" / "payload")


def test_artifact_store_rejects_large_zip_member(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "large-member.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("large.txt", "12")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    store = ArtifactStore(tmp_path)
    store.import_file(archive, digest)
    monkeypatch.setattr("liteyukibot.plugin_store._MAX_ARCHIVE_MEMBER_BYTES", 1)

    with pytest.raises(PluginStoreError, match="member is too large"):
        store.extract_zip(digest, tmp_path / "generation" / "payload")


def test_artifact_store_rejects_large_total_extracted_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "large-total.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("first.txt", "12")
        value.writestr("second.txt", "34")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    store = ArtifactStore(tmp_path)
    store.import_file(archive, digest)
    monkeypatch.setattr("liteyukibot.plugin_store._MAX_ARCHIVE_EXTRACTED_BYTES", 3)

    with pytest.raises(PluginStoreError, match="extracted size limit"):
        store.extract_zip(digest, tmp_path / "generation" / "payload")


def test_artifact_store_requires_a_verified_local_artifact(tmp_path: Path) -> None:
    archive = tmp_path / "plugin.zip"
    archive.write_bytes(b"verified payload")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    store = ArtifactStore(tmp_path)
    stored = store.import_file(archive, digest)

    assert store.require(digest) == stored
    stored.write_bytes(b"corrupt")
    with pytest.raises(PluginStoreError, match="corrupt"):
        store.require(digest)


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


def test_runtime_generation_gc_retains_active_and_previous_generations(tmp_path: Path) -> None:
    store = RuntimeGenerationStore(tmp_path)
    first = _generation("first")
    second = _generation("second")
    third = _generation("third")
    for generation in (first, second, third):
        store.write(generation)
        (store.path_for(generation.runtime_id, generation.id) / "venv").mkdir()
    store.activate("legacy", first.id)
    store.activate("legacy", second.id)

    collected = store.collect("legacy")

    assert [generation.id for generation in collected] == ["third"]
    assert [generation.id for generation in store.list_generations("legacy")] == ["first", "second"]
    assert store.active().runtime_generations == {"legacy": "second"}
    assert store.active().previous == {"legacy": "first"}
