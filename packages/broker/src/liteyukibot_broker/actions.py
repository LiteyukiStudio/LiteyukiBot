"""Typed portable actions supported by the B5 broker bridge SDK."""

from __future__ import annotations

from typing import Literal, Self

from liteyukibot_kernel.events.models import ConversationRef, FrozenModel, Message
from pydantic import Field, field_validator, model_validator

from .routing import ActionRequest

MESSAGE_SEND_KIND: Literal["message.send"] = "message.send"


def _identifier(value: str, *, field: str) -> str:
    """Implement the identifier operation for the component.

    Args:
        value: Value to validate, transform, or store.
        field: The field value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_identifier`. It delegates to `strip` while keeping
        intermediate state local to the owning operation.
    """
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must be non-empty")
    return normalized


def message_send_resource_key(owner_bridge_id: str, bot_id: str) -> str:
    """Return the exact action resource key for one bridge-owned bot.

    Args:
        owner_bridge_id: Stable identifier for the owner bridge.
        bot_id: Stable identifier for the bot.

    Returns:
        The `str` result produced by the operation.
    """

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
        """Normalize identifiers.

        Args:
            value: Value to validate, transform, or store.
            info: The info value used by the operation.

        Returns:
            The `str | None` result produced by the operation.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("message send identifiers must be strings")
        field_name = getattr(info, "field_name", "identifier")
        return _identifier(value, field=field_name)

    @model_validator(mode="after")
    def validate_route(self) -> Self:
        """Validate route.

        Returns:
            The `Self` result produced by the operation.
        """
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
    """Create the only B5 portable action request from typed data.

    Args:
        delivery_id: Stable identifier for the delivery.
        lease_id: Stable identifier for the lease.
        correlation_id: Stable identifier for the correlation.
        owner_bridge_id: Stable identifier for the owner bridge.
        payload: JSON-safe payload carried by the operation.

    Returns:
        The `ActionRequest` result produced by the operation.
    """

    return ActionRequest(
        delivery_id=delivery_id,
        lease_id=lease_id,
        correlation_id=correlation_id,
        kind=MESSAGE_SEND_KIND,
        resource_key=message_send_resource_key(owner_bridge_id, payload.bot_id),
        payload=payload.model_dump(mode="json", exclude_none=True),
    )


def parse_message_send_request(request: ActionRequest, *, owner_bridge_id: str) -> MessageSendPayload:
    """Validate that an owner received its exact bridge-scoped message action.

    Args:
        request: Validated request object to process.
        owner_bridge_id: Stable identifier for the owner bridge.

    Returns:
        The `MessageSendPayload` result produced by the operation.
    """

    if request.kind != MESSAGE_SEND_KIND:
        raise ValueError(f"expected {MESSAGE_SEND_KIND!r} action, got {request.kind!r}")
    payload = MessageSendPayload.model_validate(request.payload)
    expected_resource = message_send_resource_key(owner_bridge_id, payload.bot_id)
    if request.resource_key != expected_resource:
        raise ValueError("message.send resource key does not match the bridge-scoped bot ID")
    return payload
