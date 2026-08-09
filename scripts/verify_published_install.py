"""Verify the published distribution without importing the source checkout."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json


def _module_version(module_name: str) -> str:
    module = importlib.import_module(module_name)
    version = getattr(module, "__version__", None)
    if not isinstance(version, str):
        raise RuntimeError(f"{module_name} does not expose a string __version__")
    return version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution", default="liteyukibot-v7")
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()

    observed = {
        args.distribution: importlib.metadata.version(args.distribution),
        "liteyukibot": _module_version("liteyukibot"),
        "liteyuki": _module_version("liteyuki"),
    }
    mismatches = {
        name: version for name, version in observed.items() if version != args.expected_version
    }
    if mismatches:
        rendered = ", ".join(f"{name}={version}" for name, version in mismatches.items())
        raise RuntimeError(f"expected {args.expected_version}; observed {rendered}")

    print(json.dumps({"expected": args.expected_version, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
