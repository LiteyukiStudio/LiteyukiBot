from __future__ import annotations

from importlib import metadata
from typing import Any

import liteyukibot_functions.libraries as libraries
import pytest
from liteyukibot_functions.libraries import (
    FunctionContext,
    LibraryDefinition,
    LibraryExport,
    LibraryRegistry,
)


def _callback(_arguments: tuple[Any, ...], _context: FunctionContext) -> None:
    return None


def test_library_registry_discovers_entry_point_definitions(monkeypatch: pytest.MonkeyPatch) -> None:
    definition = LibraryDefinition(
        namespace="custom",
        provider="test-provider",
        exports=(LibraryExport("echo", _callback),),
    )

    class EntryPoint:
        name = "test-provider"

        def load(self) -> object:
            return lambda: definition

    monkeypatch.setattr(
        metadata,
        "entry_points",
        lambda *, group: (EntryPoint(),) if group == libraries.FUNCTION_LIBRARY_ENTRY_POINT_GROUP else (),
    )

    registry = LibraryRegistry.discover(include_core=False)

    assert registry.resolve("custom", "test-provider") == definition
    assert registry.export("custom", "test-provider", "echo") is definition.exports[0]


def test_library_registry_rejects_invalid_schemas_and_callbacks() -> None:
    with pytest.raises(ValueError, match="schema is invalid"):
        LibraryRegistry(
            (
                LibraryDefinition(
                    namespace="custom",
                    provider="test",
                    exports=(LibraryExport("echo", _callback, input_schema={"type": "not-a-type"}),),
                ),
            )
        )
    with pytest.raises(ValueError, match="callback must accept"):
        def invalid_callback() -> None:
            return None

        LibraryRegistry(
            (
                LibraryDefinition(
                    namespace="custom",
                    provider="test",
                    exports=(LibraryExport("echo", invalid_callback),),  # type: ignore[arg-type]
                ),
            )
        )
