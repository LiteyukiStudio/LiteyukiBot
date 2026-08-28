from __future__ import annotations

import ast
from pathlib import Path

import liteyukibot_kernel
from liteyukibot_kernel import (
    Action,
    EventBus,
    KernelStatusSnapshot,
    ServiceKey,
    ServiceRegistry,
)

ROOT = Path(__file__).parents[3]
KERNEL_SOURCE = ROOT / "packages" / "kernel" / "src" / "liteyukibot_kernel"


def test_kernel_facade_exports_contract_nucleus() -> None:
    assert EventBus is liteyukibot_kernel.EventBus
    assert ServiceRegistry is liteyukibot_kernel.ServiceRegistry
    assert Action is liteyukibot_kernel.Action
    assert not hasattr(liteyukibot_kernel, "RuntimeRequirement")
    assert not hasattr(liteyukibot_kernel, "BridgeDefinition")


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


def test_status_features_are_frozen() -> None:
    features = {"commands": "ready"}
    snapshot = KernelStatusSnapshot(
        version="7.0.0a15",
        state="running",
        uptime_seconds=1.0,
        features=features,
    )

    features["commands"] = "failed"
    assert snapshot.features == {"commands": "ready"}
    assert snapshot.as_dict()["features"] == {"commands": "ready"}


def test_service_registry_remove_respects_provider_ownership() -> None:
    registry = ServiceRegistry()
    key = ServiceKey("test.service", 1)
    registry.provide(key, object(), provider="owner")

    assert registry.remove(key, provider="other") is False
    assert registry.provider_for(key) == "owner"
    assert registry.remove(key, provider="owner") is True
    assert registry.provider_for(key) is None


def test_root_facade_does_not_advertise_webui_contracts() -> None:
    import liteyukibot

    assert not any(name.startswith("WebUi") or name.startswith("WEBUI_") for name in liteyukibot.__all__)
