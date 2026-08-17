"""Verify the installed AstrBot gateway wheel without workspace sources."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import tempfile
from pathlib import Path

import liteyukibot_runtime_astrbot
from liteyukibot_runtime_astrbot.host import AstrBotGateway

import liteyukibot
from liteyukibot.broker import BridgeCatalog
from liteyukibot.config import LoggingSettings
from liteyukibot.logging import get_logger

SOURCE_ROOT = Path(__file__).resolve().parents[1]
ASTRBOT_VERSION = "4.27.2"


async def _verify_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as directory:
        gateway = AstrBotGateway(
            Path(directory),
            "astrbot",
            get_logger(component="install-verify", runtime="astrbot"),
            LoggingSettings(),
        )

        async def sink(_ingress: object) -> None:
            return None

        try:
            await gateway.start(sink, start_pipeline=False)
            if gateway._lifecycle is None or not gateway._lifecycle.platform_manager.get_insts():
                raise RuntimeError("installed AstrBot gateway did not initialize native platform adapters")
        finally:
            await gateway.close()


def verify(expected_version: str | None = None) -> None:
    imported = (Path(liteyukibot.__file__).resolve(), Path(liteyukibot_runtime_astrbot.__file__).resolve())
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")
    definition = BridgeCatalog().discover().get("astrbot")
    if definition is None or definition.grade.value != "experimental":
        raise RuntimeError("AstrBot bridge entry point was not discovered")
    observed = {
        name: importlib.metadata.version(name)
        for name in ("liteyukibot-v7", "liteyukibot-v7-runtime-astrbot", "AstrBot")
    }
    if observed["AstrBot"] != ASTRBOT_VERSION:
        raise RuntimeError(f"expected AstrBot {ASTRBOT_VERSION}; observed {observed['AstrBot']}")
    if expected_version is not None and observed["liteyukibot-v7-runtime-astrbot"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-runtime-astrbot {expected_version}; observed {observed}")
    asyncio.run(_verify_lifecycle())
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(arguments.expected_version)
