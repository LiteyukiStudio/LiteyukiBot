"""Kernel-owned DTOs for the portable runtime API facade."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from .events import ActorRef, ConversationRef, JsonValue, Message


class RuntimeApiModel(BaseModel):
    """Frozen JSON-safe base for values crossing the Runtime API boundary."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        validate_default=True,
    )


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


__all__ = ["BotSnapshot", "EventSnapshot", "RuntimeApiModel", "SendResult"]
