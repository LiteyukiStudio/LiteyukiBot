"""Verify the installed AstrBot runtime wheel without workspace sources."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

import liteyukibot_runtime_astrbot

import liteyukibot
from liteyukibot.runtime import RuntimeCatalog

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def verify(expected_version: str | None = None) -> None:
    imported = (Path(liteyukibot.__file__).resolve(), Path(liteyukibot_runtime_astrbot.__file__).resolve())
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")
    plugin = RuntimeCatalog().discover().get("astrbot")
    if plugin is None or plugin.agent_harness != "astrbot":
        raise RuntimeError("AstrBot runtime entry point was not discovered")
    observed = {
        name: importlib.metadata.version(name)
        for name in ("liteyukibot-v7", "liteyukibot-v7-runtime-astrbot", "AstrBot")
    }
    if expected_version is not None and observed["liteyukibot-v7-runtime-astrbot"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-runtime-astrbot {expected_version}; observed {observed}")
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(arguments.expected_version)
