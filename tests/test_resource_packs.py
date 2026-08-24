from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path

import pytest

from liteyukibot.functions import (
    FunctionCall,
    FunctionDispatcher,
    FunctionDocument,
    FunctionExecutor,
    FunctionExecutorUnavailableError,
)
from liteyukibot.i18n import Translator
from liteyukibot.resource_packs import ResourceCatalog, ResourcePackError, write_resource_manifest


def _pack(root: Path, name: str, *, language: str | None = None, function: str | None = None) -> Path:
    pack = root / name
    pack.mkdir(parents=True)
    (pack / "metadata.yml").write_text(f"id: {name}\nname: {name}\nversion: 1.0.0\n", encoding="utf-8")
    if language is not None:
        language_directory = pack / "lang"
        language_directory.mkdir()
        (language_directory / "en-US.lang").write_text(language, encoding="utf-8")
    if function is not None:
        functions = pack / "functions"
        functions.mkdir()
        (functions / "hello.lyf").write_text(function, encoding="utf-8")
    write_resource_manifest(pack)
    return pack


def test_workspace_pack_overlays_builtin_language(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    _pack(resources, "custom", language="wizard.title=Custom setup\n")
    (resources / "index.json").write_text(json.dumps(["custom"]), encoding="utf-8")

    translator, warning = Translator.from_resources(ResourceCatalog.load(tmp_path), "en-US")

    assert warning is None
    assert translator.text("wizard.title") == "Custom setup"


def test_resource_catalog_reload_replaces_workspace_snapshot(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    pack = _pack(resources, "custom", language="webui.reload=before\n")
    (resources / "index.json").write_text(json.dumps(["custom"]), encoding="utf-8")
    catalog = ResourceCatalog.load(tmp_path)

    language = pack / "lang" / "en-US.lang"
    language.write_text("webui.reload=after\n", encoding="utf-8")
    write_resource_manifest(pack)
    catalog.reload(tmp_path)

    translator, _ = Translator.from_resources(catalog, "en-US")
    assert translator.text("webui.reload") == "after"


def test_enabled_package_catalogs_are_readable_and_workspace_remains_last(tmp_path: Path) -> None:
    from liteyukibot_essentials import plugin

    resources = tmp_path / "resources"
    _pack(resources, "custom", language="essentials.help_header=Custom commands\n")
    (resources / "index.json").write_text(json.dumps(["custom"]), encoding="utf-8")
    catalog = ResourceCatalog.load(tmp_path, plugin_packs=plugin.manifest.resource_packs)
    translator, _ = Translator.from_resources(catalog, "en-US")

    assert translator.text("essentials.status_summary") == "Show kernel status"
    assert translator.text("essentials.help_header") == "Custom commands"


def test_language_catalogs_overlay_keys_across_package_packs(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    _pack(resources, "one", language="shared.one=first\nshared.value=first\n")
    _pack(resources, "two", language="shared.two=second\nshared.value=second\n")
    (resources / "index.json").write_text(json.dumps(["one", "two"]), encoding="utf-8")

    translator, _ = Translator.from_resources(ResourceCatalog.load(tmp_path), "en-US")

    assert translator.text("shared.one") == "first"
    assert translator.text("shared.two") == "second"
    assert translator.text("shared.value") == "second"


def test_resource_zip_rejects_path_traversal(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    resources.mkdir()
    archive = resources / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("metadata.yml", "id: unsafe\nname: unsafe\nversion: 1\n")
        output.writestr("../outside.txt", "unsafe")
    (resources / "index.json").write_text('["unsafe.zip"]', encoding="utf-8")

    with pytest.raises(ResourcePackError, match="unsafe"):
        ResourceCatalog.load(tmp_path)


def test_resource_pack_requires_manifest(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    pack = resources / "missing"
    pack.mkdir(parents=True)
    (pack / "metadata.yml").write_text('id: missing\nname: Missing\nversion: "1"\n', encoding="utf-8")
    (resources / "index.json").write_text('["missing"]', encoding="utf-8")

    with pytest.raises(ResourcePackError, match="manifest-v1"):
        ResourceCatalog.load(tmp_path)


def test_resource_manifest_rejects_changed_content_and_unlisted_zip_file(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    pack = _pack(resources, "verified", language="verified.title=Verified\n")
    (resources / "index.json").write_text('["verified"]', encoding="utf-8")
    (pack / "lang" / "en-US.lang").write_text("verified.title=Changed\n", encoding="utf-8")

    with pytest.raises(ResourcePackError, match="digest does not match"):
        ResourceCatalog.load(tmp_path)

    write_resource_manifest(pack)
    archive = resources / "verified.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for source in pack.rglob("*"):
            if source.is_file():
                output.write(source, source.relative_to(pack).as_posix())
        output.writestr("unlisted.txt", "not allowed")
    (resources / "index.json").write_text('["verified.zip"]', encoding="utf-8")

    with pytest.raises(ResourcePackError, match="file set does not match"):
        ResourceCatalog.load(tmp_path)


def test_resource_pack_exposes_validated_presentation_metadata(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    pack = _pack(resources, "presentation")
    icon = (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + (1).to_bytes(4, "big")
        + (1).to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
    (pack / "icon.png").write_bytes(icon)
    (pack / "metadata.yml").write_text(
        "id: presentation\nname: Presentation\nversion: 1.0.0\n"
        "name_key: presentation.name\ndescription_key: presentation.description\nicon: icon.png\n",
        encoding="utf-8",
    )
    write_resource_manifest(pack)
    (resources / "index.json").write_text('["presentation"]', encoding="utf-8")

    catalog = ResourceCatalog.load(tmp_path)

    assert catalog.pack("presentation").name_key == "presentation.name"
    assert catalog.pack("presentation").description_key == "presentation.description"
    assert catalog.icon("presentation") is not None


def test_resource_pack_exposes_declared_kind(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    pack = _pack(resources, "language", language="language.title=Language\n")
    (pack / "metadata.yml").write_text(
        "id: language\nname: Language\nversion: 1.0.0\nkind: language\n",
        encoding="utf-8",
    )
    write_resource_manifest(pack)
    (resources / "index.json").write_text('["language"]', encoding="utf-8")

    catalog = ResourceCatalog.load(tmp_path)

    assert catalog.pack("language").kind == "language"


def test_resource_pack_rejects_unknown_kind(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    pack = _pack(resources, "invalid")
    (pack / "metadata.yml").write_text(
        "id: invalid\nname: Invalid\nversion: 1.0.0\nkind: other\n",
        encoding="utf-8",
    )
    write_resource_manifest(pack)
    (resources / "index.json").write_text('["invalid"]', encoding="utf-8")

    with pytest.raises(ResourcePackError, match="kind is unsupported"):
        ResourceCatalog.load(tmp_path)


def test_resource_pack_rejects_non_alpha_icon(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    pack = _pack(resources, "presentation")
    icon = (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + (1).to_bytes(4, "big")
        + (1).to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
    (pack / "icon.png").write_bytes(icon)
    (pack / "metadata.yml").write_text(
        "id: presentation\nname: Presentation\nversion: 1.0.0\nicon: icon.png\n",
        encoding="utf-8",
    )
    write_resource_manifest(pack)
    (resources / "index.json").write_text('["presentation"]', encoding="utf-8")

    with pytest.raises(ResourcePackError, match="alpha"):
        ResourceCatalog.load(tmp_path)


def test_function_dispatch_reports_missing_executor(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    _pack(resources, "functions", function="return nothing")
    (resources / "index.json").write_text('["functions"]', encoding="utf-8")
    dispatcher = FunctionDispatcher(ResourceCatalog.load(tmp_path), executors={})

    with pytest.raises(FunctionExecutorUnavailableError, match="no executor"):
        asyncio.run(dispatcher.dispatch(FunctionCall("hello", {})))


def test_function_dispatches_to_matching_external_executor(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    _pack(resources, "functions", function="return value")
    (resources / "index.json").write_text('["functions"]', encoding="utf-8")

    class Executor:
        extensions: tuple[str, ...] = (".lyf",)

        async def execute(self, document: FunctionDocument, call: FunctionCall, _invoke: object) -> object:
            return {"id": call.id, "source": document.read_text()}

    executor: FunctionExecutor = Executor()
    dispatcher = FunctionDispatcher(ResourceCatalog.load(tmp_path), executors={".lyf": executor})

    assert asyncio.run(dispatcher.dispatch(FunctionCall("hello", {}))) == {"id": "hello", "source": "return value"}
