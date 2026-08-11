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
from liteyukibot.resource_packs import ResourceCatalog, ResourcePackError


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
    return pack


def test_workspace_pack_overlays_builtin_language(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    _pack(resources, "custom", language="wizard.title=Custom setup\n")
    (resources / "index.json").write_text(json.dumps(["custom"]), encoding="utf-8")

    translator, warning = Translator.from_resources(ResourceCatalog.load(tmp_path), "en-US")

    assert warning is None
    assert translator.text("wizard.title") == "Custom setup"


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
