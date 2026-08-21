from __future__ import annotations

import pytest

from liteyukibot.broker import RuntimeApiOperation, runtime_api_catalog


def _operation(name: str = "snapshot") -> RuntimeApiOperation:
    return RuntimeApiOperation(
        namespace="event",
        operation=name,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )


def test_runtime_api_catalog_binds_default_capability_to_provider_kind() -> None:
    declarations = runtime_api_catalog("astrbot", (_operation(),))

    assert declarations[0].api_id == "event.snapshot"
    assert declarations[0].capabilities == ("runtime.astrbot.event.snapshot",)


def test_runtime_api_operation_accepts_provider_specific_extra_capabilities() -> None:
    operation = RuntimeApiOperation(
        namespace="event",
        operation="snapshot",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        capabilities=("runtime.*.event.snapshot", "runtime.astrbot.event.debug"),
    )

    declaration = operation.declaration("astrbot")

    assert declaration.capabilities == (
        "runtime.astrbot.event.snapshot",
        "runtime.astrbot.event.debug",
    )


def test_runtime_api_catalog_rejects_duplicate_operations() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        runtime_api_catalog("astrbot", (_operation(), _operation()))


def test_runtime_api_operation_requires_standard_capability() -> None:
    with pytest.raises(ValueError, match="include"):
        RuntimeApiOperation(
            namespace="event",
            operation="snapshot",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            capabilities=("runtime.astrbot.event.snapshot",),
        )
