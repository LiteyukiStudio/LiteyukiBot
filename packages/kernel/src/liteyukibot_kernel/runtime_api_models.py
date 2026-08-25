"""Kernel-owned DTOs for the portable runtime API facade."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from .events import ActorRef, ConversationRef, JsonValue, Message
from .events.models import _freeze_json, _thaw_json, _validate_json_value


class RuntimeApiModel(BaseModel):
    """Frozen JSON-safe base for values crossing the Runtime API boundary."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        validate_default=True,
    )

    @field_validator("extensions", mode="before", check_fields=False)
    @classmethod
    def validate_extensions(cls, value: Any) -> Any:
        """Validate extension data before Pydantic container conversion.

        Args:
            value: Candidate extension mapping.

        Returns:
            The validated input for normal field parsing.
        """

        _validate_json_value(value, "extensions")
        return value

    @field_validator("extensions", mode="after", check_fields=False)
    @classmethod
    def freeze_extensions(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        """Recursively freeze an extension mapping.

        Args:
            value: Validated extension mapping.

        Returns:
            The immutable JSON-safe mapping.
        """

        return cast(Mapping[str, JsonValue], _freeze_json(value))

    @field_serializer("extensions", check_fields=False)
    def serialize_extensions(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        """Serialize immutable extension mappings as normal JSON objects.

        Args:
            value: Immutable extension mapping.

        Returns:
            A mutable JSON representation for serialization.
        """

        return {key: _thaw_json(item) for key, item in value.items()}


class EventSnapshot(RuntimeApiModel):
    """Portable identity and content projection of one active source event."""

    source_event_id: str = Field(min_length=1)
    runtime_id: str = Field(min_length=1)
    adapter: str = Field(min_length=1)
    bot_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    conversation: ConversationRef
    actor: ActorRef | None = None
    message: Message | None = None
    extensions: Mapping[str, JsonValue] = Field(default_factory=dict)


class BotSnapshot(RuntimeApiModel):
    """Portable identity and capability projection of one provider bot."""

    bot_id: str = Field(min_length=1)
    adapter: str = Field(min_length=1)
    capabilities: tuple[str, ...] = ()
    extensions: Mapping[str, JsonValue] = Field(default_factory=dict)


class SendResult(RuntimeApiModel):
    """Portable result envelope for provider-owned message sends."""

    sent: bool
    result: JsonValue = None
    extensions: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("result", mode="before")
    @classmethod
    def validate_result(cls, value: Any) -> Any:
        """Validate provider result data before container conversion.

        Args:
            value: Candidate JSON-safe provider result.

        Returns:
            The validated input for normal field parsing.
        """

        _validate_json_value(value, "result")
        return value

    @field_validator("result", mode="after")
    @classmethod
    def freeze_result(cls, value: JsonValue) -> JsonValue:
        """Recursively freeze provider result data.

        Args:
            value: Validated provider result.

        Returns:
            The immutable JSON-safe result.
        """

        return _freeze_json(value)

    @field_serializer("result")
    def serialize_result(self, value: JsonValue) -> Any:
        """Serialize immutable provider result data as JSON containers.

        Args:
            value: Immutable provider result.

        Returns:
            A mutable JSON representation for serialization.
        """

        return _thaw_json(value)


__all__ = ["BotSnapshot", "EventSnapshot", "RuntimeApiModel", "SendResult"]
