"""Verify the installed agent resolver wheel without workspace sources."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

import liteyukibot_agent_resolver

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def verify(expected_version: str | None = None) -> None:
    imported = Path(liteyukibot_agent_resolver.__file__).resolve()
    if imported.is_relative_to(SOURCE_ROOT):
        raise RuntimeError(f"workspace source import detected: {imported}")
    observed = {
        "liteyukibot-v7-agent-resolver": importlib.metadata.version("liteyukibot-v7-agent-resolver"),
    }
    if expected_version is not None and observed["liteyukibot-v7-agent-resolver"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-agent-resolver {expected_version}; observed {observed}")
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(arguments.expected_version)
