from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

type JsonValue = None | bool | int | float | str | tuple[JsonValue, ...] | Mapping[str, JsonValue]
type SegmentType = Literal["text", "mention", "reply", "image"]
type ConversationType = Literal["private", "group"]


def _new_id() -> str:
    """Implement the new id operation for the component.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_new_id`. It delegates to `uuid4` while keeping intermediate
        state local to the owning operation.
    """
    return str(uuid4())


def _utc_now() -> datetime:
    """Implement the utc now operation for the component.

    Returns:
        The `datetime` result produced by the operation.

    Notes:
        Internal implementation detail for `_utc_now`. It delegates to `now` while keeping intermediate
        state local to the owning operation.
    """
    return datetime.now(UTC)


def _validate_json_value(value: Any, path: str = "value") -> None:
    """Validate json value.

    Args:
        value: Value to validate, transform, or store.
        path: Filesystem or logical resource path.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_validate_json_value`. It delegates to `isfinite`,
        `enumerate`, `_validate_json_value`, `items` while keeping intermediate state local to the
        owning operation.
    """
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain NaN or infinity")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} must use string object keys")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise ValueError(f"{path} contains non-JSON value {type(value).__name__}")


def _freeze_json(value: JsonValue) -> JsonValue:
    """Freeze json.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `JsonValue` result produced by the operation.

    Notes:
        Internal implementation detail for `_freeze_json`. It delegates to `_freeze_json`, `items` while
        keeping intermediate state local to the owning operation.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: JsonValue) -> None | bool | int | float | str | list[Any] | dict[str, Any]:
    """Implement the thaw json operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `None | bool | int | float | str | list[Any] | dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_thaw_json`. It delegates to `_thaw_json`, `items` while
        keeping intermediate state local to the owning operation.
    """
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


class FrozenModel(BaseModel):
    """Represent the validated frozen model contract."""
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False, validate_default=True)


class Segment(FrozenModel):
    """Represent the validated segment contract."""
    type: SegmentType
    data: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("data", mode="before")
    @classmethod
    def validate_data_is_json(cls, value: Any) -> Any:
        """Validate data is json.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Any` result produced by the operation.
        """
        _validate_json_value(value, "data")
        return value

    @field_validator("data", mode="after")
    @classmethod
    def freeze_data(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        """Freeze data.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, JsonValue]` result produced by the operation.
        """
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})

    @field_serializer("data")
    def serialize_data(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        """Implement the serialize data operation for the segment.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        return {key: _thaw_json(item) for key, item in value.items()}

    @model_validator(mode="after")
    def validate_normalized_shape(self) -> Self:
        """Validate normalized shape.

        Returns:
            The `Self` result produced by the operation.
        """
        if self.type == "text" and not isinstance(self.data.get("text"), str):
            raise ValueError("text segments require a string data.text")
        if self.type == "mention":
            if self.data.get("scope") != "all" and not isinstance(self.data.get("user_id"), str):
                raise ValueError("mention segments require data.user_id or data.scope=all")
        if self.type == "reply" and not isinstance(self.data.get("message_id"), str):
            raise ValueError("reply segments require a string data.message_id")
        if self.type == "image" and not isinstance(self.data.get("url"), str):
            raise ValueError("image segments require a string data.url")
        return self


class Message(FrozenModel):
    """Represent the validated message contract."""
    segments: tuple[Segment, ...] = ()

    @property
    def plain_text(self) -> str:
        """Return the message's plain text.

        Returns:
            The `str` result produced by the operation.
        """
        return "".join(
            text
            for segment in self.segments
            if segment.type == "text" and isinstance((text := segment.data.get("text")), str)
        )


class ActorRef(FrozenModel):
    """Represent the validated actor ref contract."""
    id: str = Field(min_length=1)
    display_name: str | None = None
    is_bot: bool = False


class ConversationRef(FrozenModel):
    """Represent the validated conversation ref contract."""
    id: str = Field(min_length=1)
    type: ConversationType
    parent_id: str | None = None

    @property
    def ordering_key(self) -> str:
        """Return the conversation ref's ordering key.

        Returns:
            The `str` result produced by the operation.
        """
        return f"{self.type}:{self.id}"


class EventEnvelope(FrozenModel):
    """Represent the validated event envelope contract."""
    schema_version: Literal[1] = 1
    id: str = Field(default_factory=_new_id, min_length=1)
    timestamp: datetime = Field(default_factory=_utc_now)
    received_at: datetime = Field(default_factory=_utc_now)
    runtime_id: str = Field(min_length=1)
    adapter: str = Field(min_length=1)
    bot_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    conversation: ConversationRef
    actor: ActorRef | None = None
    message: Message | None = None
    reply_token: str | None = None
    raw: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("raw", mode="before")
    @classmethod
    def validate_raw_is_json(cls, value: Any) -> Any:
        """Validate raw is json.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Any` result produced by the operation.
        """
        _validate_json_value(value, "raw")
        return value

    @field_validator("raw", mode="after")
    @classmethod
    def freeze_raw(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        """Freeze raw.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, JsonValue]` result produced by the operation.
        """
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})

    @field_serializer("raw")
    def serialize_raw(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        """Implement the serialize raw operation for the event envelope.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        return {key: _thaw_json(item) for key, item in value.items()}

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        """Validate timestamps.

        Returns:
            The `Self` result produced by the operation.
        """
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.received_at.tzinfo is None or self.received_at.utcoffset() is None:
            raise ValueError("received_at must be timezone-aware")
        return self

    @property
    def ordering_key(self) -> tuple[str, str, str]:
        """Return the event envelope's ordering key.

        Returns:
            The `tuple[str, str, str]` result produced by the operation.
        """
        return self.runtime_id, self.bot_id, self.conversation.ordering_key


class SendMessage(FrozenModel):
    """Represent the validated send message contract."""
    type: Literal["send_message"] = "send_message"
    message: Message
    conversation: ConversationRef | None = None
    reply_token: str | None = None

    @model_validator(mode="after")
    def validate_route(self) -> Self:
        """Validate route.

        Returns:
            The `Self` result produced by the operation.
        """
        if self.conversation is None and not self.reply_token:
            raise ValueError("send_message requires conversation or reply_token")
        return self


type Action = SendMessage


class ActionEnvelope(FrozenModel):
    """Represent the validated action envelope contract."""
    schema_version: Literal[1] = 1
    action_id: str = Field(default_factory=_new_id, min_length=1)
    event_id: str | None = None
    runtime_id: str = Field(min_length=1)
    bot_id: str = Field(min_length=1)
    action: Action


class ActionResult(FrozenModel):
    """Represent the validated action result contract."""
    schema_version: Literal[1] = 1
    action_id: str = Field(min_length=1)
    success: bool
    data: JsonValue = None
    error_code: str | None = None
    error_message: str | None = None

    @field_validator("data", mode="before")
    @classmethod
    def validate_data_is_json(cls, value: Any) -> Any:
        """Validate data is json.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Any` result produced by the operation.
        """
        _validate_json_value(value, "data")
        return value

    @field_validator("data", mode="after")
    @classmethod
    def freeze_data(cls, value: JsonValue) -> JsonValue:
        """Freeze data.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `JsonValue` result produced by the operation.
        """
        return _freeze_json(value)

    @field_serializer("data")
    def serialize_data(self, value: JsonValue) -> Any:
        """Implement the serialize data operation for the action result.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Any` result produced by the operation.
        """
        return _thaw_json(value)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        """Validate outcome.

        Returns:
            The `Self` result produced by the operation.
        """
        if self.success and (self.error_code is not None or self.error_message is not None):
            raise ValueError("successful action results cannot contain an error")
        if not self.success and not self.error_code:
            raise ValueError("failed action results require error_code")
        return self


class HandlerResult(FrozenModel):
    """Represent the validated handler result contract."""
    actions: tuple[ActionEnvelope, ...] = ()
    stop_propagation: bool = False


class HandlerFailure(FrozenModel):
    """Represent the validated handler failure contract."""
    handler: str
    kind: Literal["timeout", "error", "invalid_result"]
    message: str


class DispatchResult(FrozenModel):
    """Represent the validated dispatch result contract."""
    event_id: str
    status: Literal["processed", "overloaded", "closed"]
    handlers_called: int = 0
    stopped: bool = False
    action_results: tuple[ActionResult, ...] = ()
    failures: tuple[HandlerFailure, ...] = ()
