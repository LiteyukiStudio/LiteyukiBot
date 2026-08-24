"""Verify developer-kit wheels without importing the source checkout."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import tempfile
from pathlib import Path
from typing import Any

import liteyukibot
from liteyukibot import PluginDefinition
from liteyukibot.events import (
    ActorRef,
    ConversationRef,
    EventEnvelope,
    Message,
    Segment,
)
from liteyukibot.testing import PluginTestHarness

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
IMPORTED_LITEYUKIBOT = Path(liteyukibot.__file__).resolve()
PY_TYPED_MARKER = IMPORTED_LITEYUKIBOT.with_name("py.typed")
HAS_PY_TYPED = PY_TYPED_MARKER.is_file()


def _event() -> EventEnvelope:
    return EventEnvelope(
        runtime_id="adapter-runtime",
        adapter="example",
        bot_id="bot-1",
        type="message",
        conversation=ConversationRef(id="conversation-1", type="group"),
        actor=ActorRef(id="user-1"),
        message=Message(segments=(Segment(type="text", data={"text": "installed"}),)),
        reply_token="reply-1",
    )


def _installed_plugin() -> PluginDefinition:
    matches = tuple(
        item
        for item in importlib.metadata.entry_points(group="liteyukibot.plugins")
        if item.name == "example.echo"
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected one example.echo entry point, found {len(matches)}")
    candidate: Any = matches[0].load()
    if not isinstance(candidate, PluginDefinition):
        raise TypeError("example.echo did not resolve to PluginDefinition")
    if candidate.manifest.id != matches[0].name:
        raise RuntimeError("example.echo entry-point name and manifest id differ")
    return candidate


async def verify() -> dict[str, Any]:
    if IMPORTED_LITEYUKIBOT.is_relative_to(SOURCE_ROOT):
        raise RuntimeError(
            f"liteyukibot imported from source checkout: {IMPORTED_LITEYUKIBOT}"
        )
    if not HAS_PY_TYPED:
        raise RuntimeError(f"installed package is missing py.typed: {PY_TYPED_MARKER}")

    with tempfile.TemporaryDirectory() as directory:
        async with PluginTestHarness(
            _installed_plugin(),
            root=Path(directory),
            config={"prefix": "wheel: "},
        ) as plugin_harness:
            dispatch = await plugin_harness.publish(_event())
            if dispatch.status != "processed" or len(plugin_harness.recorded_actions) != 1:
                raise RuntimeError("installed plugin did not process the test Event")

    return {
        "liteyukibot": str(IMPORTED_LITEYUKIBOT),
        "plugin": "example.echo",
        "py_typed": str(PY_TYPED_MARKER),
    }


def main() -> int:
    print(json.dumps(asyncio.run(verify()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
