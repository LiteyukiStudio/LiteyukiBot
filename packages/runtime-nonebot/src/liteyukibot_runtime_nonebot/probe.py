"""Startup probe for a materialized managed NoneBot plugin generation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import nonebot

from .host import _managed_load_plan


def probe(generation: Path) -> None:
    """Initialize NoneBot and load every plugin declared by one generation.

    Args:
        generation: Materialized generation directory containing load-plan.json.

    Returns:
        None after every module and directory loads successfully.

    Security:
        This deliberately executes the candidate plugin set before activation
        with the current OS user's privileges. It detects startup failures but
        does not sandbox hostile plugin code.
    """
    plugins, directories = _managed_load_plan(str(generation.resolve(strict=True)))
    nonebot.init()
    failures: list[str] = []
    for plugin in plugins:
        if nonebot.load_plugin(plugin) is None:
            failures.append(plugin)
    for directory in directories:
        loaded: set[Any] = nonebot.load_plugins(directory)
        if not loaded:
            failures.append(directory)
    if failures:
        raise RuntimeError(f"NoneBot generation probe failed to load: {', '.join(failures)}")


def main() -> int:
    """Parse the generation path and execute the startup probe.

    Returns:
        Zero when the complete load plan succeeds.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generation", type=Path)
    args = parser.parse_args()
    probe(args.generation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
