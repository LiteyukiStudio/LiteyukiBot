from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

import liteyukibot.resource_packs as resource_packs
from liteyukibot.resource_packs import (
    ResourceCatalog,
    ResourceFile,
    ResourcePack,
    ResourcePackError,
    ResourcePackMetadata,
    write_resource_manifest,
)


def test_resource_zip_rejects_duplicate_entries(tmp_path: Path) -> None:
    archive_path = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("metadata.yml", "id: duplicate\n")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("metadata.yml", "id: duplicate-again\n")

    with pytest.raises(ResourcePackError, match="duplicate"):
        resource_packs._load_zip(archive_path)


def test_resource_zip_rejects_unsafe_compression_ratio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resource_packs, "_RESOURCE_MAX_COMPRESSION_RATIO", 2)
    archive_path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("metadata.yml", "id: bomb\n", compress_type=zipfile.ZIP_STORED)
        archive.writestr("payload.txt", "x" * 4096, compress_type=zipfile.ZIP_DEFLATED)

    with pytest.raises(ResourcePackError, match="compression ratio"):
        resource_packs._load_zip(archive_path)


def test_resource_zip_enforces_file_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resource_packs, "_RESOURCE_MAX_FILE_BYTES", 4)
    archive_path = tmp_path / "large.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("metadata.yml", "id: too-large\n")

    with pytest.raises(ResourcePackError, match="file exceeds 4 bytes"):
        resource_packs._load_zip(archive_path)


def test_resource_zip_enforces_file_count_before_loading_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource_packs, "_RESOURCE_MAX_FILES", 1)
    archive_path = tmp_path / "many-files.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("metadata.yml", "id: many\n")
        archive.writestr("payload.txt", "payload")

    with pytest.raises(ResourcePackError, match="more than 1 files"):
        resource_packs._load_zip(archive_path)


def test_resource_directory_enforces_file_count_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resource_packs, "_RESOURCE_MAX_FILES", 1)
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "metadata.yml").write_text("id: limited\n", encoding="utf-8")
    (pack / "manifest-v1.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ResourcePackError, match="more than 1 files"):
        resource_packs._load_directory(pack, "test")


def test_resource_zip_keeps_the_validated_content_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "metadata.yml").write_text("id: snapshot\n", encoding="utf-8")
    (source / "payload.txt").write_text("original", encoding="utf-8")
    write_resource_manifest(source)

    archive_path = tmp_path / "snapshot.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in source.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())

    pack = resource_packs._load_zip(archive_path)
    (source / "payload.txt").write_text("replacement", encoding="utf-8")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("metadata.yml", "id: snapshot\n")
        archive.writestr("payload.txt", "replacement")
        archive.writestr("manifest-v1.json", (source / "manifest-v1.json").read_bytes())

    assert pack.files["payload.txt"].read_text() == "original"


def test_resource_catalog_enforces_pack_count_and_memory_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    def pack(pack_id: str, size: int) -> ResourcePack:
        metadata = ResourcePackMetadata(pack_id, pack_id, "1", "", "test")
        file = ResourceFile(pack_id, "payload", lambda: b"x" * size)
        return ResourcePack(metadata, {"payload": file})

    monkeypatch.setattr(resource_packs, "_RESOURCE_CATALOG_MAX_PACKS", 1)
    with pytest.raises(ResourcePackError, match="more than 1 packs"):
        ResourceCatalog((pack("one", 1), pack("two", 1)))

    monkeypatch.setattr(resource_packs, "_RESOURCE_CATALOG_MAX_PACKS", 256)
    monkeypatch.setattr(resource_packs, "_RESOURCE_CATALOG_MAX_BYTES", 1)
    with pytest.raises(ResourcePackError, match="in-memory bytes"):
        ResourceCatalog((pack("one", 1), pack("two", 1)))


def test_public_resource_pack_snapshots_file_readers_and_mapping() -> None:
    content = b"original"
    files = {
        "payload": ResourceFile("snapshot", "payload", lambda: content),
    }
    metadata = ResourcePackMetadata("snapshot", "snapshot", "1", "", "test")
    pack = ResourcePack(metadata, files)
    content = b"replacement"
    files["other"] = ResourceFile("snapshot", "other", lambda: b"other")

    assert pack.size_bytes == len(b"original")
    assert pack.files["payload"].read_bytes() == b"original"
    assert "other" not in pack.files


def test_resource_index_is_bounded_before_json_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    resources = tmp_path / "resources"
    resources.mkdir()
    (resources / "index.json").write_text(json.dumps(["pack"]), encoding="utf-8")
    monkeypatch.setattr(resource_packs, "_RESOURCE_MAX_INDEX_BYTES", 4)

    with pytest.raises(ResourcePackError, match="exceeds 4 bytes"):
        list(resource_packs._load_workspace_packs(tmp_path))
