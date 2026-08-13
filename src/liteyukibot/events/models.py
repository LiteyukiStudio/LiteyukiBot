from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

type JsonValue = None | bool | int | float | str | tuple[JsonValue, ...] | Mapping[str, JsonValue]
type SegmentType = Literal["text", "media", "mention", "reply", "adapter"]
type ConversationType = Literal["private", "group", "channel", "thread", "unknown"]


def _new_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _validate_json_value(value: Any, path: str = "value") -> None:
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
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: JsonValue) -> None | bool | int | float | str | list[Any] | dict[str, Any]:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False, validate_default=True)


class Segment(FrozenModel):
    type: SegmentType
    data: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("data", mode="before")
    @classmethod
    def validate_data_is_json(cls, value: Any) -> Any:
        _validate_json_value(value, "data")
        return value

    @field_validator("data", mode="after")
    @classmethod
    def freeze_data(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})

    @field_serializer("data")
    def serialize_data(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return {key: _thaw_json(item) for key, item in value.items()}

    @model_validator(mode="after")
    def validate_normalized_shape(self) -> Self:
        if self.type == "text" and not isinstance(self.data.get("text"), str):
            raise ValueError("text segments require a string data.text")
        return self


class Message(FrozenModel):
    segments: tuple[Segment, ...] = ()

    @property
    def plain_text(self) -> str:
        return "".join(
            text
            for segment in self.segments
            if segment.type == "text" and isinstance((text := segment.data.get("text")), str)
        )


class ActorRef(FrozenModel):
    id: str = Field(min_length=1)
    display_name: str | None = None
    is_bot: bool = False


class ConversationRef(FrozenModel):
    id: str = Field(min_length=1)
    type: ConversationType = "unknown"
    parent_id: str | None = None

    @property
    def ordering_key(self) -> str:
        return f"{self.type}:{self.id}"


class EventEnvelope(FrozenModel):
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
        _validate_json_value(value, "raw")
        return value

    @field_validator("raw", mode="after")
    @classmethod
    def freeze_raw(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})

    @field_serializer("raw")
    def serialize_raw(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return {key: _thaw_json(item) for key, item in value.items()}

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.received_at.tzinfo is None or self.received_at.utcoffset() is None:
            raise ValueError("received_at must be timezone-aware")
        return self

    @property
    def ordering_key(self) -> tuple[str, str, str]:
        return self.runtime_id, self.bot_id, self.conversation.ordering_key


class SendMessage(FrozenModel):
    type: Literal["send_message"] = "send_message"
    message: Message
    conversation: ConversationRef | None = None
    reply_token: str | None = None

    @model_validator(mode="after")
    def validate_route(self) -> Self:
        if self.conversation is None and not self.reply_token:
            raise ValueError("send_message requires conversation or reply_token")
        return self


class EditMessage(FrozenModel):
    """Replace a platform message previously created by this bot."""

    type: Literal["edit_message"] = "edit_message"
    message_id: str = Field(min_length=1)
    message: Message
    conversation: ConversationRef | None = None


class CallApi(FrozenModel):
    type: Literal["call_api"] = "call_api"
    api: str = Field(min_length=1)
    params: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("params", mode="before")
    @classmethod
    def validate_params_are_json(cls, value: Any) -> Any:
        _validate_json_value(value, "params")
        return value

    @field_validator("params", mode="after")
    @classmethod
    def freeze_params(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})

    @field_serializer("params")
    def serialize_params(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return {key: _thaw_json(item) for key, item in value.items()}


type Action = Annotated[SendMessage | EditMessage | CallApi, Field(discriminator="type")]


class ActionEnvelope(FrozenModel):
    schema_version: Literal[1] = 1
    action_id: str = Field(default_factory=_new_id, min_length=1)
    event_id: str | None = None
    runtime_id: str = Field(min_length=1)
    bot_id: str = Field(min_length=1)
    action: Action


class ActionResult(FrozenModel):
    schema_version: Literal[1] = 1
    action_id: str = Field(min_length=1)
    success: bool
    data: JsonValue = None
    error_code: str | None = None
    error_message: str | None = None

    @field_validator("data", mode="before")
    @classmethod
    def validate_data_is_json(cls, value: Any) -> Any:
        _validate_json_value(value, "data")
        return value

    @field_validator("data", mode="after")
    @classmethod
    def freeze_data(cls, value: JsonValue) -> JsonValue:
        return _freeze_json(value)

    @field_serializer("data")
    def serialize_data(self, value: JsonValue) -> Any:
        return _thaw_json(value)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.success and (self.error_code is not None or self.error_message is not None):
            raise ValueError("successful action results cannot contain an error")
        if not self.success and not self.error_code:
            raise ValueError("failed action results require error_code")
        return self


class HandlerResult(FrozenModel):
    actions: tuple[ActionEnvelope, ...] = ()
    stop_propagation: bool = False


class HandlerFailure(FrozenModel):
    handler: str
    kind: Literal["timeout", "error", "invalid_result"]
    message: str


class DispatchResult(FrozenModel):
    event_id: str
    status: Literal["processed", "overloaded", "closed"]
    handlers_called: int = 0
    stopped: bool = False
    action_results: tuple[ActionResult, ...] = ()
    failures: tuple[HandlerFailure, ...] = ()
