"""Version 6 broker bridge-registration messages carried by LYIP frames."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from ..lyip import LyipError, LyipFrame, LyipLane

BROKER_PROTOCOL_VERSION: Final = 6
BROKER_REGISTER_TYPE_ID: Final = 600
BROKER_REGISTERED_TYPE_ID: Final = 601
BROKER_REJECTED_TYPE_ID: Final = 602
BROKER_UNREGISTER_TYPE_ID: Final = 603
BROKER_UNREGISTERED_TYPE_ID: Final = 604


class BrokerWireError(LyipError):
    """Raised when a LYIP frame does not carry a valid broker v6 message."""


class BridgeAccess(StrEnum):
    FULL = "full"
    LIMITED = "limited"


class BrokerWireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _non_blank_identifier(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("identifier must be non-empty")
    return normalized


class ActionResourceDeclaration(BrokerWireModel):
    """An action kind and resource namespace owned by one bridge."""

    kind: str
    resource_prefix: str

    @field_validator("kind", "resource_prefix", mode="before")
    @classmethod
    def validate_identifier(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("action resource fields must be strings")
        return _non_blank_identifier(value)


class BridgeManifest(BrokerWireModel):
    """Static declarations authenticated during one bridge registration."""

    bridge_id: str
    access: BridgeAccess
    subscriptions: tuple[str, ...] = ()
    action_resources: tuple[ActionResourceDeclaration, ...] = ()

    @field_validator("bridge_id", mode="before")
    @classmethod
    def validate_bridge_id(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("bridge identifier must be a string")
        return _non_blank_identifier(value)

    @field_validator("subscriptions", mode="before")
    @classmethod
    def validate_declarations(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise TypeError("bridge declarations must be a JSON array")
        declarations: list[str] = []
        for declaration in value:
            if not isinstance(declaration, str):
                raise TypeError("bridge declaration must be a string")
            declarations.append(_non_blank_identifier(declaration))
        if len(declarations) != len(set(declarations)):
            raise ValueError("bridge declarations must not contain duplicates")
        return tuple(declarations)

    @model_validator(mode="after")
    def validate_action_resources(self) -> BridgeManifest:
        keys = {(resource.kind, resource.resource_prefix) for resource in self.action_resources}
        if len(keys) != len(self.action_resources):
            raise ValueError("action resources must not contain duplicates")
        return self


class BridgeRegister(BrokerWireModel):
    type: Literal["bridge.register"] = "bridge.register"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    bridge_id: str
    instance_token: str
    manifest: BridgeManifest

    @field_validator("bridge_id", "instance_token", mode="before")
    @classmethod
    def validate_identifiers(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("bridge registration fields must be strings")
        return _non_blank_identifier(value)

    @model_validator(mode="after")
    def validate_manifest_bridge(self) -> BridgeRegister:
        if self.bridge_id != self.manifest.bridge_id:
            raise ValueError("registration bridge identifier must match manifest")
        return self


class BridgeRegistered(BrokerWireModel):
    type: Literal["bridge.registered"] = "bridge.registered"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    session_id: str

    @field_validator("session_id", mode="before")
    @classmethod
    def validate_session_id(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("session identifier must be a string")
        return _non_blank_identifier(value)


class BridgeRejected(BrokerWireModel):
    type: Literal["bridge.rejected"] = "bridge.rejected"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    code: str
    message: str

    @field_validator("code", "message", mode="before")
    @classmethod
    def validate_rejection_fields(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("rejection fields must be strings")
        return _non_blank_identifier(value)


class BridgeUnregister(BrokerWireModel):
    type: Literal["bridge.unregister"] = "bridge.unregister"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    session_id: str

    @field_validator("session_id", mode="before")
    @classmethod
    def validate_session_id(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("session identifier must be a string")
        return _non_blank_identifier(value)


class BridgeUnregistered(BrokerWireModel):
    type: Literal["bridge.unregistered"] = "bridge.unregistered"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    session_id: str

    @field_validator("session_id", mode="before")
    @classmethod
    def validate_session_id(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("session identifier must be a string")
        return _non_blank_identifier(value)


type BrokerWireMessage = Annotated[
    BridgeRegister | BridgeRegistered | BridgeRejected | BridgeUnregister | BridgeUnregistered,
    Field(discriminator="type"),
]
BROKER_WIRE_ADAPTER: Final[TypeAdapter[BrokerWireMessage]] = TypeAdapter(BrokerWireMessage)

_TYPE_IDS: Final[dict[type[BrokerWireModel], int]] = {
    BridgeRegister: BROKER_REGISTER_TYPE_ID,
    BridgeRegistered: BROKER_REGISTERED_TYPE_ID,
    BridgeRejected: BROKER_REJECTED_TYPE_ID,
    BridgeUnregister: BROKER_UNREGISTER_TYPE_ID,
    BridgeUnregistered: BROKER_UNREGISTERED_TYPE_ID,
}
_MESSAGE_TYPES: Final[dict[int, type[BrokerWireModel]]] = {type_id: model for model, type_id in _TYPE_IDS.items()}


def encode_broker_message(
    message: BrokerWireMessage,
    *,
    generation: int,
    stream_id: str,
    sequence: int,
    lease_id: str,
) -> LyipFrame:
    """Encode one v6 control-plane message into an existing LYIP frame."""

    return LyipFrame(
        protocol=1,
        generation=generation,
        lane=LyipLane.CONTROL,
        type_id=_TYPE_IDS[type(message)],
        stream_id=stream_id,
        sequence=sequence,
        lease_id=lease_id,
        payload=message.model_dump_json(exclude_none=True).encode("utf-8"),
    )


def decode_broker_message(frame: LyipFrame) -> BrokerWireMessage:
    """Decode a v6 broker control message without accepting legacy runtime types."""

    if frame.lane is not LyipLane.CONTROL:
        raise BrokerWireError("broker control message arrived on the wrong LYIP lane")
    message_type = _MESSAGE_TYPES.get(frame.type_id)
    if message_type is None:
        raise BrokerWireError(f"unknown broker v6 type ID: {frame.type_id}")
    try:
        message = message_type.model_validate_json(frame.payload)
    except ValueError as error:
        raise BrokerWireError("broker v6 payload is invalid") from error
    if _TYPE_IDS[type(message)] != frame.type_id:
        raise BrokerWireError("broker v6 type ID does not match payload type")
    return message  # type: ignore[return-value]
