"""Verify the standalone kernel wheel without importing workspace sources."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
from pathlib import Path

import liteyukibot_kernel
from liteyukibot_kernel import EventBus, ServiceRegistry, ServiceRequirement

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def verify(*, expected_version: str | None = None) -> None:
    imported = Path(liteyukibot_kernel.__file__).resolve()
    if imported.is_relative_to(SOURCE_ROOT):
        raise RuntimeError(f"workspace source import detected: {imported}")
    if importlib.util.find_spec("liteyukibot") is not None:
        raise RuntimeError("standalone kernel installation unexpectedly provides the root composition package")

    installed = importlib.metadata.version("liteyukibot-v7-kernel")
    if expected_version is not None and installed != expected_version:
        raise RuntimeError(f"expected kernel version {expected_version}, found {installed}")
    if liteyukibot_kernel.__version__ != installed:
        raise RuntimeError("kernel module and distribution versions disagree")

    if not callable(EventBus) or not callable(ServiceRegistry) or not callable(ServiceRequirement):
        raise RuntimeError("kernel contract exports are incomplete")

    print(json.dumps({"liteyukibot-v7-kernel": installed}, sort_keys=True))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(expected_version=arguments.expected_version)
