"""Typed portable actions supported by the B5 broker bridge SDK."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from ..events.models import ConversationRef, FrozenModel, Message
from .routing import ActionRequest

MESSAGE_SEND_KIND: Literal["message.send"] = "message.send"


def _identifier(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must be non-empty")
    return normalized


def message_send_resource_key(owner_bridge_id: str, bot_id: str) -> str:
    """Return the exact action resource key for one bridge-owned bot."""

    return f"bot:{_identifier(owner_bridge_id, field='owner_bridge_id')}:{_identifier(bot_id, field='bot_id')}"


class MessageSendPayload(FrozenModel):
    """Protocol-neutral contents of a portable ``message.send`` action."""

    bot_id: str = Field(min_length=1)
    message: Message
    conversation: ConversationRef | None = None
    reply_token: str | None = Field(default=None, min_length=1)

    @field_validator("bot_id", "reply_token", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: object, info: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("message send identifiers must be strings")
        field_name = getattr(info, "field_name", "identifier")
        return _identifier(value, field=field_name)

    @model_validator(mode="after")
    def validate_route(self) -> Self:
        if self.conversation is None and self.reply_token is None:
            raise ValueError("message.send requires conversation or reply_token")
        return self


def make_message_send_request(
    *,
    delivery_id: str,
    lease_id: str,
    correlation_id: str,
    owner_bridge_id: str,
    payload: MessageSendPayload,
) -> ActionRequest:
    """Create the only B5 portable action request from typed data."""

    return ActionRequest(
        delivery_id=delivery_id,
        lease_id=lease_id,
        correlation_id=correlation_id,
        kind=MESSAGE_SEND_KIND,
        resource_key=message_send_resource_key(owner_bridge_id, payload.bot_id),
        payload=payload.model_dump(mode="json", exclude_none=True),
    )


def parse_message_send_request(request: ActionRequest, *, owner_bridge_id: str) -> MessageSendPayload:
    """Validate that an owner received its exact bridge-scoped message action."""

    if request.kind != MESSAGE_SEND_KIND:
        raise ValueError(f"expected {MESSAGE_SEND_KIND!r} action, got {request.kind!r}")
    payload = MessageSendPayload.model_validate(request.payload)
    expected_resource = message_send_resource_key(owner_bridge_id, payload.bot_id)
    if request.resource_key != expected_resource:
        raise ValueError("message.send resource key does not match the bridge-scoped bot ID")
    return payload
