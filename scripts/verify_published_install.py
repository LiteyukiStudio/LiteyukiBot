"""Verify the published distribution without importing the source checkout."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _module_version(module_name: str) -> str:
    module = importlib.import_module(module_name)
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        raise RuntimeError(f"{module_name} does not expose __file__")
    if Path(module_file).resolve().is_relative_to(SOURCE_ROOT):
        raise RuntimeError(f"workspace source import detected: {module_file}")
    version = getattr(module, "__version__", None)
    if not isinstance(version, str):
        raise RuntimeError(f"{module_name} does not expose a string __version__")
    return version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution", default="liteyukibot-v7")
    parser.add_argument("--expected-version")
    args = parser.parse_args()

    distribution_version = importlib.metadata.version(args.distribution)
    expected_version = args.expected_version or distribution_version
    observed = {
        args.distribution: distribution_version,
        "liteyukibot": _module_version("liteyukibot"),
    }
    mismatches = {
        name: version for name, version in observed.items() if version != expected_version
    }
    if mismatches:
        rendered = ", ".join(f"{name}={version}" for name, version in mismatches.items())
        raise RuntimeError(f"expected {expected_version}; observed {rendered}")

    print(json.dumps({"expected": expected_version, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
