"""Verify the installed OneBot adapter wheel without workspace sources."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
from pathlib import Path

import liteyukibot_adapter_onebot
import liteyukibot_kernel
from liteyukibot_adapter_onebot import OneBotService, SnowLumaAccountSettings, normalize_event

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def verify(expected_version: str | None = None) -> None:
    imported = tuple(
        Path(module.__file__).resolve()  # type: ignore[arg-type]
        for module in (liteyukibot_kernel, liteyukibot_adapter_onebot)
    )
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")
    if importlib.util.find_spec("liteyukibot") is not None:
        raise RuntimeError("standalone OneBot adapter unexpectedly provides the root package")
    if importlib.util.find_spec("liteyukibot_runtime_adapter") is not None:
        raise RuntimeError("retired runtime-adapter package remains importable")
    if importlib.util.find_spec("liteyukibot_broker") is not None:
        raise RuntimeError("retired broker package remains importable")
    if not callable(OneBotService) or not callable(SnowLumaAccountSettings) or not callable(normalize_event):
        raise RuntimeError("OneBot v11 SnowLuma contracts are incomplete")
    observed = {
        "liteyukibot-v7-kernel": importlib.metadata.version("liteyukibot-v7-kernel"),
        "liteyukibot-v7-adapter-onebot": importlib.metadata.version("liteyukibot-v7-adapter-onebot"),
    }
    if expected_version is not None and any(version != expected_version for version in observed.values()):
        raise RuntimeError(f"expected all OneBot adapter dependencies at {expected_version}; observed {observed}")
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(arguments.expected_version)
