"""Verify the installed v6 runtime wheel without workspace sources."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

import liteyuki
import liteyukibot_runtime_v6

import liteyukibot
from liteyukibot.broker import BridgeCatalog, BridgeSupportGrade

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def verify(expected_version: str | None = None) -> None:
    imported = (
        Path(liteyukibot.__file__).resolve(),
        Path(liteyukibot_runtime_v6.__file__).resolve(),
        Path(liteyuki.__file__).resolve(),
    )
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")
    bridge = BridgeCatalog().discover().get("v6")
    if bridge is None:
        raise RuntimeError("v6 bridge entry point was not discovered")
    if bridge.grade is not BridgeSupportGrade.EXPERIMENTAL:
        raise RuntimeError(f"unexpected v6 bridge support grade: {bridge.grade}")
    if any(entry.name == "v6" for entry in importlib.metadata.entry_points(group="liteyukibot.runtimes")):
        raise RuntimeError("v6 package must not publish a legacy runtime entry point")
    observed = {name: importlib.metadata.version(name) for name in ("liteyukibot-v7", "liteyukibot-v7-runtime-v6")}
    if expected_version is not None and observed["liteyukibot-v7-runtime-v6"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-runtime-v6 {expected_version}; observed {observed}")
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(arguments.expected_version)
