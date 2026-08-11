"""Verify the installed v6 runtime wheel without workspace sources."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

import liteyuki
import liteyukibot_runtime_v6

import liteyukibot
from liteyukibot.runtime import RuntimeCatalog

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def verify(expected_version: str | None = None) -> None:
    imported = (
        Path(liteyukibot.__file__).resolve(),
        Path(liteyukibot_runtime_v6.__file__).resolve(),
        Path(liteyuki.__file__).resolve(),
    )
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")
    plugin = RuntimeCatalog().discover().get("v6")
    if plugin is None:
        raise RuntimeError("v6 runtime entry point was not discovered")
    if plugin.command[2:] != ("liteyukibot_runtime_v6",):
        raise RuntimeError(f"unexpected v6 runtime command: {plugin.command}")
    if not plugin.default_event_route_messages_only:
        raise RuntimeError("v6 runtime must declare its default message event route")
    observed = {name: importlib.metadata.version(name) for name in ("liteyukibot-v7", "liteyukibot-v7-runtime-v6")}
    if expected_version is not None and observed["liteyukibot-v7-runtime-v6"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-runtime-v6 {expected_version}; observed {observed}")
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(arguments.expected_version)
