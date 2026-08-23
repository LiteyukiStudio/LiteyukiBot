"""Verify the installed NoneBot runtime wheel without workspace sources."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

import liteyukibot_runtime_nonebot

import liteyukibot

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def verify(expected_version: str | None = None) -> None:
    imported = (Path(liteyukibot.__file__).resolve(), Path(liteyukibot_runtime_nonebot.__file__).resolve())
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")
    entry_points = importlib.metadata.entry_points(group="liteyukibot.bridges")
    bridge = next((entry for entry in entry_points if entry.name == "nonebot"), None)
    if bridge is None:
        raise RuntimeError("NoneBot bridge entry point was not discovered")
    if bridge.value != "liteyukibot_runtime_nonebot:bridge_definition":
        raise RuntimeError(f"unexpected NoneBot bridge entry point: {bridge.value}")
    definition = bridge.load()()
    if (
        definition.kind != "nonebot"
        or definition.grade != "stable"
        or definition.distribution != "liteyukibot-v7-runtime-nonebot"
        or definition.facet_installer is None
        or definition.probe_module != "liteyukibot_runtime_nonebot"
    ):
        raise RuntimeError(f"unexpected NoneBot bridge definition: {definition!r}")
    legacy = [
        entry for entry in importlib.metadata.entry_points(group="liteyukibot.runtimes") if entry.name == "nonebot"
    ]
    if legacy:
        raise RuntimeError("NoneBot package must not publish a legacy runtime entry point")
    observed = {
        name: importlib.metadata.version(name)
        for name in ("liteyukibot-v7", "liteyukibot-v7-runtime-nonebot")
    }
    if expected_version is not None and observed["liteyukibot-v7-runtime-nonebot"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-runtime-nonebot {expected_version}; observed {observed}")
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(arguments.expected_version)
