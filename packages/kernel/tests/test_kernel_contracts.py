from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, cast

import liteyukibot_kernel
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from liteyukibot_kernel import (
    Action,
    ActionEnvelope,
    AdapterAction,
    DeleteMessage,
    EventBus,
    EventEnvelope,
    KernelStatusSnapshot,
    RespondRequest,
    ServiceKey,
    ServiceRegistry,
)

ROOT = Path(__file__).parents[3]
KERNEL_SOURCE = ROOT / "packages" / "kernel" / "src" / "liteyukibot_kernel"
JSON_VALUES = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=-(2**53), max_value=2**53)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=32),
    lambda children: st.lists(children, max_size=4)
    | st.dictionaries(st.text(max_size=12), children, max_size=4),
    max_leaves=12,
)
JSON_OBJECTS = st.dictionaries(st.text(max_size=12), JSON_VALUES, max_size=5)


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


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        ({"type": "delete_message", "message_id": "-7"}, DeleteMessage),
        ({"type": "respond_request", "approve": False, "reason": "denied"}, RespondRequest),
        (
            {"type": "adapter_action", "adapter": "test", "name": "inspect", "params": {"id": "1"}},
            AdapterAction,
        ),
    ],
)
def test_action_envelope_uses_a_discriminated_public_action_union(
    payload: dict[str, object],
    expected_type: type[object],
) -> None:
    envelope = ActionEnvelope.model_validate(
        {"runtime_id": "runtime", "bot_id": "bot", "action": payload}
    )
    assert isinstance(envelope.action, expected_type)


@settings(max_examples=100, deadline=None)
@given(JSON_OBJECTS)
def test_event_details_and_adapter_params_preserve_arbitrary_json(values: dict[str, object]) -> None:
    expected = json.loads(json.dumps(values, ensure_ascii=False, allow_nan=False))
    event = EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="notice.test",
        details=cast(Any, values),
    )
    action = ActionEnvelope(
        event_id=event.id,
        runtime_id=event.runtime_id,
        bot_id=event.bot_id,
        action=AdapterAction(adapter="test", name="operation", params=cast(Any, values)),
    )

    values["mutated_after_construction"] = True
    assert event.model_dump(mode="json")["details"] == expected
    assert action.model_dump(mode="json")["action"]["params"] == expected
    assert EventEnvelope.model_validate_json(event.model_dump_json()) == event
    assert ActionEnvelope.model_validate_json(action.model_dump_json()) == action
    with pytest.raises(TypeError):
        event.details["forbidden"] = True  # type: ignore[index]
