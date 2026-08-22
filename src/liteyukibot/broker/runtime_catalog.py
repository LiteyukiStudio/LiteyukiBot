"""Reusable declarations for provider-owned runtime API catalogs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from ..runtime_api_models import BotSnapshot, EventSnapshot, SendResult
from .protocol import RuntimeApiDeclaration

PORTABLE_RUNTIME_API_VERSION = "1.2"


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field} must be a non-empty trimmed string")
    return value


@dataclass(frozen=True, slots=True)
class RuntimeApiOperation:
    """One provider operation with its portable schema and capability."""

    namespace: str
    operation: str
    input_schema: Mapping[str, object]
    output_schema: Mapping[str, object]
    version: str = "1.1"
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.namespace, "runtime API namespace")
        _identifier(self.operation, "runtime API operation")
        _identifier(self.version, "runtime API version")
        expected = f"runtime.*.{self.namespace}.{self.operation}"
        capabilities = self.capabilities or (expected,)
        if len(capabilities) != len(set(capabilities)) or any(
            not _identifier(item, "runtime API capability") for item in capabilities
        ):
            raise ValueError("runtime API capabilities must be unique non-empty strings")
        if expected not in capabilities:
            raise ValueError(f"runtime API capabilities must include {expected!r}")
        object.__setattr__(self, "capabilities", capabilities)

    def declaration(self, runtime_kind: str) -> RuntimeApiDeclaration:
        """Bind this operation to one authenticated runtime provider kind."""

        runtime_kind = _identifier(runtime_kind, "runtime API runtime kind")
        capability_prefix = f"runtime.{runtime_kind}.{self.namespace}.{self.operation}"
        capabilities = tuple(
            capability_prefix if item == f"runtime.*.{self.namespace}.{self.operation}" else item
            for item in self.capabilities
        )
        return RuntimeApiDeclaration(
            runtime_kind=runtime_kind,
            namespace=self.namespace,
            operation=self.operation,
            version=self.version,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            capabilities=capabilities,
        )


def runtime_api_catalog(
    runtime_kind: str, operations: Sequence[RuntimeApiOperation]
) -> tuple[RuntimeApiDeclaration, ...]:
    """Build and validate the immutable catalog advertised by one bridge."""

    declarations = tuple(operation.declaration(runtime_kind) for operation in operations)
    identifiers = tuple(declaration.api_id for declaration in declarations)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("runtime API catalog must not contain duplicate operations")
    return declarations


def portable_message_schema() -> dict[str, object]:
    """Return the Draft 2020-12 schema for the protocol-neutral Message DTO."""

    return {
        "type": "object",
        "properties": {
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["text", "media", "mention", "reply", "adapter"]},
                        "data": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["type", "data"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["segments"],
        "additionalProperties": False,
    }


def portable_conversation_schema() -> dict[str, object]:
    """Return the Draft 2020-12 schema for the ConversationRef DTO."""

    return {
        "type": "object",
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "type": {"type": "string", "enum": ["private", "group", "channel", "thread", "unknown"]},
            "parent_id": {"type": ["string", "null"]},
        },
        "required": ["id"],
        "additionalProperties": False,
    }


def portable_event_snapshot_schema() -> dict[str, object]:
    """Return the canonical EventSnapshot JSON schema."""

    return cast(dict[str, object], EventSnapshot.model_json_schema())


def portable_bot_snapshot_schema() -> dict[str, object]:
    """Return the canonical BotSnapshot JSON schema."""

    return cast(dict[str, object], BotSnapshot.model_json_schema())


def portable_send_result_schema() -> dict[str, object]:
    """Return the canonical SendResult JSON schema."""

    return cast(dict[str, object], SendResult.model_json_schema())


__all__ = [
    "PORTABLE_RUNTIME_API_VERSION",
    "RuntimeApiOperation",
    "portable_bot_snapshot_schema",
    "portable_conversation_schema",
    "portable_event_snapshot_schema",
    "portable_message_schema",
    "portable_send_result_schema",
    "runtime_api_catalog",
]
