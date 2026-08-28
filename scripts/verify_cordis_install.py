"""Verify the installed Cordis wheel without importing workspace sources."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
from pathlib import Path

import liteyukibot_cordis
import liteyukibot_kernel
from liteyukibot_cordis import CordisManager, Scope

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def verify(expected_version: str | None = None) -> None:
    imported = (Path(liteyukibot_cordis.__file__).resolve(), Path(liteyukibot_kernel.__file__).resolve())
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")
    if importlib.util.find_spec("liteyukibot") is not None:
        raise RuntimeError("standalone Cordis installation unexpectedly provides the root package")
    if not callable(CordisManager) or not callable(Scope):
        raise RuntimeError("Cordis public contracts are incomplete")

    observed = {
        "liteyukibot-v7-kernel": importlib.metadata.version("liteyukibot-v7-kernel"),
        "liteyukibot-v7-cordis": importlib.metadata.version("liteyukibot-v7-cordis"),
    }
    if expected_version is not None and any(version != expected_version for version in observed.values()):
        raise RuntimeError(f"expected all Cordis dependencies at {expected_version}; observed {observed}")

    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(arguments.expected_version)
