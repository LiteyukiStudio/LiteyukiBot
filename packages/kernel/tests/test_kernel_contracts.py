from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, cast

import liteyukibot_kernel
import pytest
from liteyukibot_kernel import (
    BotSnapshot,
    EventBus,
    KernelStatusSnapshot,
    RuntimeRequirement,
    SendResult,
    ServiceRegistry,
)

ROOT = Path(__file__).parents[3]
KERNEL_SOURCE = ROOT / "packages" / "kernel" / "src" / "liteyukibot_kernel"


def test_kernel_facade_exports_contract_nucleus() -> None:
    assert EventBus is liteyukibot_kernel.EventBus
    assert ServiceRegistry is liteyukibot_kernel.ServiceRegistry
    assert RuntimeRequirement is liteyukibot_kernel.RuntimeRequirement


def test_kernel_source_never_imports_root_composition() -> None:
    imports: set[str] = set()
    for path in KERNEL_SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
                imports.add(node.module)

    assert not any(name == "liteyukibot" or name.startswith("liteyukibot.") for name in imports)


def test_root_compatibility_paths_share_kernel_identity() -> None:
    from liteyukibot.bridge_contracts import BridgeDefinition as CompatibleBridgeDefinition
    from liteyukibot.events import EventBus as CompatibleEventBus
    from liteyukibot.services import ServiceRegistry as CompatibleServiceRegistry

    assert CompatibleBridgeDefinition is liteyukibot_kernel.BridgeDefinition
    assert CompatibleEventBus is EventBus
    assert CompatibleServiceRegistry is ServiceRegistry


def test_status_runtime_health_is_deeply_frozen_and_json_safe() -> None:
    health: dict[str, Any] = {"nested": {"items": [{"ok": True}]}}
    snapshot = KernelStatusSnapshot(
        version="7.0.0a14",
        state="running",
        uptime_seconds=1.0,
        runtime_health={"runtime": cast(Any, health)},
    )

    health["nested"]["items"][0]["ok"] = False
    frozen_health = cast(Any, snapshot.runtime_health["runtime"])
    assert frozen_health["nested"]["items"][0]["ok"] is True
    with pytest.raises(TypeError):
        frozen_health["nested"]["changed"] = True
    assert snapshot.as_dict()["runtime_health"] == {
        "runtime": {"nested": {"items": [{"ok": True}]}}
    }

    with pytest.raises(ValueError, match="non-JSON"):
        KernelStatusSnapshot(
            version="7.0.0a14",
            state="running",
            uptime_seconds=1.0,
            runtime_health=cast(Any, {"runtime": {"bad": object()}}),
        )


def test_runtime_api_json_fields_are_deeply_frozen() -> None:
    extensions: dict[str, Any] = {"nested": {"items": [{"ok": True}]}}
    result: dict[str, Any] = {"messages": [{"id": "one"}]}
    bot = BotSnapshot(bot_id="bot", adapter="test", extensions=cast(Any, extensions))
    sent = SendResult(sent=True, result=cast(Any, result))

    extensions["nested"]["items"][0]["ok"] = False
    result["messages"][0]["id"] = "changed"
    frozen_extensions = cast(Any, bot.extensions)
    frozen_result = cast(Any, sent.result)
    assert frozen_extensions["nested"]["items"][0]["ok"] is True
    assert frozen_result["messages"][0]["id"] == "one"
    with pytest.raises(TypeError):
        frozen_extensions["nested"]["changed"] = True
    assert bot.model_dump(mode="json")["extensions"] == {"nested": {"items": [{"ok": True}]}}
    assert sent.model_dump(mode="json")["result"] == {"messages": [{"id": "one"}]}


def test_root_facade_does_not_advertise_webui_contracts() -> None:
    import liteyukibot

    assert not any(name.startswith("WebUi") or name.startswith("WEBUI_") for name in liteyukibot.__all__)
