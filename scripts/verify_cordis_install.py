"""Verify the installed Cordis wheel without importing workspace sources."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import liteyukibot_cordis

import liteyukibot
from liteyukibot.config import CordisSettings
from liteyukibot.events import EventBus

SOURCE_ROOT = Path(__file__).resolve().parents[1]


class _Actions:
    async def execute(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("verification does not execute actions")


def verify() -> None:
    imported = (Path(liteyukibot.__file__).resolve(), Path(liteyukibot_cordis.__file__).resolve())
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")

    matches = tuple(
        item for item in importlib.metadata.entry_points(group="liteyukibot.cordis_hosts") if item.name == "python"
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected one Cordis host entry point, found {len(matches)}")
    factory = matches[0].load()
    host = factory(events=EventBus(), actions=_Actions(), settings=CordisSettings(enabled=("verify",)), logger=None)
    if not callable(getattr(host, "start", None)) or not callable(getattr(host, "aclose", None)):
        raise RuntimeError("Cordis host entry point returned an invalid host")

    print(
        json.dumps(
            {
                "liteyukibot-v7": importlib.metadata.version("liteyukibot-v7"),
                "liteyukibot-v7-cordis": importlib.metadata.version("liteyukibot-v7-cordis"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    verify()
