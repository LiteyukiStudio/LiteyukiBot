"""Verify the installed v6 function executor wheel without workspace sources."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import liteyukibot_functions

import liteyukibot
from liteyukibot.functions import FunctionCall, FunctionDispatcher
from liteyukibot.resource_packs import ResourceCatalog, write_resource_manifest

SOURCE_ROOT = Path(__file__).resolve().parents[1]


class _Capabilities:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    async def call_api(self, api: str, params: Mapping[str, Any]) -> None:
        self.calls.append((api, params))


def _verify_import_sources() -> None:
    imported = (Path(liteyukibot.__file__).resolve(), Path(liteyukibot_functions.__file__).resolve())
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")


async def verify(expected_version: str | None = None) -> None:
    _verify_import_sources()
    executors = FunctionDispatcher.discover_executors()
    if set(liteyukibot_functions.V6FunctionExecutor.extensions) - set(executors):
        raise RuntimeError("v6 function executor entry point was not discovered")

    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        pack = workspace / "resources" / "legacy"
        functions = pack / "functions"
        functions.mkdir(parents=True)
        (pack / "metadata.yml").write_text('id: legacy\nname: Legacy\nversion: "6"\n', encoding="utf-8")
        (workspace / "resources" / "index.json").write_text('["legacy"]', encoding="utf-8")
        (functions / "verify.lyf").write_text("api verify value=1\n", encoding="utf-8")
        write_resource_manifest(pack)
        capabilities = _Capabilities()
        await FunctionDispatcher(ResourceCatalog.load(workspace)).dispatch(
            FunctionCall("verify", {}, capabilities=capabilities)
        )
        if capabilities.calls != [("verify", {"value": 1})]:
            raise RuntimeError(f"unexpected v6 function result: {capabilities.calls!r}")

    observed = {name: importlib.metadata.version(name) for name in ("liteyukibot-v7", "liteyukibot-v7-functions")}
    if expected_version is not None and observed["liteyukibot-v7-functions"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-functions {expected_version}; observed {observed}")
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    asyncio.run(verify(arguments.expected_version))
