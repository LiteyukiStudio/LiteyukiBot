from __future__ import annotations

import pytest
from liteyukibot_broker import (
    RuntimeApiOperation,
    portable_runtime_api_catalog,
    portable_runtime_api_catalog_fingerprint,
    portable_runtime_api_operations,
    runtime_api_catalog,
)


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


def test_portable_runtime_catalog_is_complete_and_fingerprinted() -> None:
    operations = portable_runtime_api_operations()
    declarations = portable_runtime_api_catalog("astrbot")

    operation_ids = tuple(f"{operation.namespace}.{operation.operation}" for operation in operations)
    assert operation_ids == (
        "event.snapshot",
        "event.send",
        "bot.snapshot",
        "bot.send",
    )
    assert tuple(declaration.api_id for declaration in declarations) == operation_ids
    fingerprint = portable_runtime_api_catalog_fingerprint("astrbot")
    assert len(fingerprint) == 64


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
