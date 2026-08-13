"""Verify the installed MoFox runtime wheel without workspace sources."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import tempfile
from pathlib import Path

import liteyukibot_runtime_mofox
from liteyukibot_runtime_mofox.host import MoFoxHeadlessEngine

import liteyukibot
from liteyukibot.runtime import RuntimeCatalog

SOURCE_ROOT = Path(__file__).resolve().parents[1]
NEO_MOFOX_COMMIT = "e2ee2ff73b494428bbdfd983c7569c6f074a9c76"


def _verify_locked_upstream() -> str:
    distribution = importlib.metadata.distribution("neo-mofox")
    source = distribution.read_text("direct_url.json")
    if source is None:
        raise RuntimeError("neo-mofox installation does not record its locked source commit")
    document = json.loads(source)
    vcs = document.get("vcs_info")
    commit = vcs.get("commit_id") if isinstance(vcs, dict) else None
    if commit != NEO_MOFOX_COMMIT:
        raise RuntimeError(f"expected neo-mofox commit {NEO_MOFOX_COMMIT}; observed {commit!r}")
    return distribution.version


async def _verify_lifecycle() -> None:
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as directory:
        engine = MoFoxHeadlessEngine(Path(directory), {})
        try:
            await engine.start()
            if engine._bot is None or engine._bot.scheduler is None:
                raise RuntimeError("installed MoFox runtime did not create a scheduler")
        finally:
            await engine.close()
    if Path.cwd() != original_cwd:
        raise RuntimeError("installed MoFox runtime did not restore the working directory after shutdown")


def verify(expected_version: str | None = None) -> None:
    imported = (Path(liteyukibot.__file__).resolve(), Path(liteyukibot_runtime_mofox.__file__).resolve())
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")
    plugin = RuntimeCatalog().discover().get("mofox")
    if plugin is None or plugin.agent_harness != "mofox":
        raise RuntimeError("MoFox runtime entry point was not discovered")
    observed = {name: importlib.metadata.version(name) for name in ("liteyukibot-v7", "liteyukibot-v7-runtime-mofox")}
    observed["neo-mofox"] = _verify_locked_upstream()
    if expected_version is not None and observed["liteyukibot-v7-runtime-mofox"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-runtime-mofox {expected_version}; observed {observed}")
    asyncio.run(_verify_lifecycle())
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(arguments.expected_version)
