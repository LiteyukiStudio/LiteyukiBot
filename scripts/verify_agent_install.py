"""Verify the installed Agent bridge wheel without workspace sources."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import tempfile
from pathlib import Path

import liteyukibot_agent
from liteyukibot_agent.catalog import AgentCatalog
from liteyukibot_agent.store import ConversationStore
from liteyukibot_agent_resolver import AgentToolDescriptor
from liteyukibot_broker import BridgeSupportGrade

import liteyukibot
from liteyukibot.broker.service import BridgeCatalog

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _verify_bridge_contract() -> None:
    bridges = BridgeCatalog().discover()
    for kind in ("agent", "agent-sandbox"):
        definition = bridges.get(kind)
        if definition is None:
            raise RuntimeError(f"bridge entry point {kind!r} was not discovered")
        if definition.grade is not BridgeSupportGrade.EXPERIMENTAL:
            raise RuntimeError(f"bridge {kind!r} must remain experimental in Alpha6")
        if definition.distribution != "liteyukibot-v7-agent":
            raise RuntimeError(f"bridge {kind!r} declared an unexpected distribution")

    if any(
        entry.name == "agent"
        for entry in importlib.metadata.entry_points(group="liteyukibot.runtimes")
    ):
        raise RuntimeError("legacy Agent runtime entry point is still installed")
    if any(
        entry.name == "liteyuki.agent" or entry.name == "liteyukibot.agent"
        for entry in importlib.metadata.entry_points(group="liteyukibot.plugins")
    ):
        raise RuntimeError("legacy liteyukibot.agent plugin entry point is still installed")


def _verify_catalog_bounds() -> None:
    tools = tuple(
        AgentToolDescriptor(
            id=f"docs.item-{index}",
            module_id="docs",
            title=f"Documentation item {index}",
            description="Searchable documentation item.",
            input_schema={"type": "object"},
        )
        for index in range(40)
    )
    catalog = AgentCatalog(tools)
    if len(catalog.initial()) != 7:
        raise RuntimeError("Agent initial Tool catalog bound is incorrect")
    if len(catalog.search("documentation").tools) != 8:
        raise RuntimeError("Agent catalog search bound is incorrect")


def _verify_history_store() -> None:
    with tempfile.TemporaryDirectory() as directory:
        store = ConversationStore(Path(directory) / "history.sqlite3")
        try:
            for value in ("first", "second", "third"):
                store.append("nonebot", "bot-1", "group:one", "user", value, retain=2)
            store.append("nonebot", "bot-1", "group:two", "user", "unrelated", retain=2)
            if store.messages("nonebot", "bot-1", "group:one", limit=10) != [
                {"role": "user", "content": "second"},
                {"role": "user", "content": "third"},
            ]:
                raise RuntimeError("Agent history retention did not bound one conversation")
            if store.clear("nonebot", "bot-1", "group:one") != 2:
                raise RuntimeError("Agent history clear did not report removed messages")
            if store.messages("nonebot", "bot-1", "group:two", limit=10) != [
                {"role": "user", "content": "unrelated"}
            ]:
                raise RuntimeError("Agent history clear crossed source conversation boundaries")
        finally:
            store.close()


def verify(expected_version: str | None = None) -> None:
    imported = (Path(liteyukibot.__file__).resolve(), Path(liteyukibot_agent.__file__).resolve())
    if any(path.is_relative_to(SOURCE_ROOT) for path in imported):
        raise RuntimeError(f"workspace source import detected: {imported}")

    observed = {
        name: importlib.metadata.version(name)
        for name in (
            "liteyukibot-v7",
            "liteyukibot-v7-agent",
            "liteyukibot-v7-agent-resolver",
            "liteyukibot-v7-commands",
            "liteyukibot-v7-permissions",
        )
    }
    if expected_version is not None and observed["liteyukibot-v7-agent"] != expected_version:
        raise RuntimeError(f"expected liteyukibot-v7-agent {expected_version}; observed {observed}")
    _verify_bridge_contract()
    _verify_catalog_bounds()
    _verify_history_store()
    print(json.dumps(observed, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    verify(arguments.expected_version)
