"""Verify the installed OneBot adapter wheel without workspace sources."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

import liteyukibot_adapter_onebot
import liteyukibot_runtime_adapter
from liteyukibot_broker import BridgeSupportGrade
from liteyukibot_runtime_adapter.host import discover_adapter_plugins

import liteyukibot

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def verify(expected_version: str | None = None) -> None:
    imported = tuple(
        Path(module.__file__).resolve()  # type: ignore[arg-type]
        for module in (liteyukibot, liteyukibot_runtime_adapter, liteyukibot_adapter_onebot)
    )
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")
    plugins = discover_adapter_plugins()
    if tuple(plugins) != ("onebot-v11", "onebot-v12"):
        raise RuntimeError(f"OneBot adapter entry point was not discovered: {plugins}")
    if plugins["onebot-v11"].grade is not BridgeSupportGrade.STABLE:
        raise RuntimeError("OneBot v11 adapter must be stable")
    if plugins["onebot-v12"].grade is not BridgeSupportGrade.EXPERIMENTAL:
        raise RuntimeError("OneBot v12 adapter must be experimental")
    observed = {
        name: importlib.metadata.version(name)
        for name in (
            "liteyukibot-v7",
            "liteyukibot-v7-runtime-adapter",
            "liteyukibot-v7-adapter-onebot",
        )
    }
    if expected_version is not None and observed["liteyukibot-v7-adapter-onebot"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-adapter-onebot {expected_version}; observed {observed}")
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(arguments.expected_version)
