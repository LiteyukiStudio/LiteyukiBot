"""Version 6 broker bridge-registration messages carried by LYIP frames."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_serializer, model_validator

from ..lyip import LyipError, LyipFrame, LyipLane

BROKER_PROTOCOL_VERSION: Final = 6
BROKER_REGISTER_TYPE_ID: Final = 600
BROKER_REGISTERED_TYPE_ID: Final = 601
BROKER_REJECTED_TYPE_ID: Final = 602
BROKER_UNREGISTER_TYPE_ID: Final = 603
BROKER_UNREGISTERED_TYPE_ID: Final = 604
BROKER_DIAGNOSTICS_STATUS_TYPE_ID: Final = 605
BROKER_DIAGNOSTICS_LIST_TYPE_ID: Final = 606
BROKER_DIAGNOSTICS_DETAIL_TYPE_ID: Final = 607
BROKER_DIAGNOSTICS_STATUS_RESULT_TYPE_ID: Final = 608
BROKER_DIAGNOSTICS_LIST_RESULT_TYPE_ID: Final = 609
BROKER_DIAGNOSTICS_DETAIL_RESULT_TYPE_ID: Final = 610


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
    """An action kind and exact or prefix resource owned by one bridge."""

    kind: str
    resource: str | None = None
    resource_prefix: str | None = None

    @field_validator("kind", "resource", "resource_prefix", mode="before")
    @classmethod
    def validate_identifier(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("action resource fields must be strings")
        return _non_blank_identifier(value)

    @model_validator(mode="after")
    def validate_match_mode(self) -> ActionResourceDeclaration:
        if (self.resource is None) == (self.resource_prefix is None):
            raise ValueError("action resource declarations must define exactly one of resource or resource_prefix")
        return self

    @model_serializer
    def serialize(self) -> dict[str, str]:
        result = {"kind": self.kind}
        if self.resource is not None:
            result["resource"] = self.resource
        if self.resource_prefix is not None:
            result["resource_prefix"] = self.resource_prefix
        return result

    def matches(self, resource_key: str) -> bool:
        """Return whether this declaration owns the supplied resource key."""

        if self.resource is not None:
            return resource_key == self.resource
        assert self.resource_prefix is not None
        return resource_key.startswith(self.resource_prefix)

    @property
    def is_exact(self) -> bool:
        return self.resource is not None


class BrokerToolDeclaration(BrokerWireModel):
    """Immutable Tool declaration projected by the authenticated kernel bridge."""

    id: str
    description: str
    input_schema: Mapping[str, object]
    output_schema: Mapping[str, object]
    capabilities: tuple[str, ...] = ()

    @field_validator("id", "description", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("tool declaration fields must be strings")
        return _non_blank_identifier(value)

    @field_validator("capabilities", mode="before")
    @classmethod
    def validate_capabilities(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise TypeError("tool capabilities must be an array")
        result = tuple(_non_blank_identifier(item) for item in value if isinstance(item, str))
        if len(result) != len(value) or len(result) != len(set(result)):
            raise ValueError("tool capabilities must be unique strings")
        return result


class AuthorizationContextWire(BrokerWireModel):
    """Only event identity and principal fields may cross the Tool wire."""

    event_id: str
    runtime_id: str
    bot_id: str
    actor_id: str | None = None

    @field_validator("event_id", "runtime_id", "bot_id", "actor_id", mode="before")
    @classmethod
    def validate_context_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("authorization context fields must be strings")
        return _non_blank_identifier(value)


class BridgeManifest(BrokerWireModel):
    """Static declarations authenticated during one bridge registration."""

    bridge_id: str
    access: BridgeAccess
    subscriptions: tuple[str, ...] = ()
    action_resources: tuple[ActionResourceDeclaration, ...] = ()
    tools: tuple[BrokerToolDeclaration, ...] = ()

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
        keys = tuple(
            (resource.kind, resource.resource, resource.resource_prefix) for resource in self.action_resources
        )
        if len(set(keys)) != len(self.action_resources):
            raise ValueError("action resources must not contain duplicates")
        tool_ids = tuple(tool.id for tool in self.tools)
        if len(tool_ids) != len(set(tool_ids)):
            raise ValueError("tool declarations must not contain duplicate IDs")
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


class BrokerDiagnosticsStatus(BrokerWireModel):
    """Authenticate and request bounded broker diagnostic status."""

    type: Literal["broker.diagnostics.status"] = "broker.diagnostics.status"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    token: str

    @field_validator("token", mode="before")
    @classmethod
    def validate_token(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("diagnostics token must be a string")
        return _non_blank_identifier(value)


class BrokerDiagnosticsList(BrokerWireModel):
    """Authenticate and request one redacted event-delivery page."""

    type: Literal["broker.diagnostics.list"] = "broker.diagnostics.list"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    token: str
    cursor: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    state: str | None = None
    topic: str | None = None
    source: str | None = None
    target: str | None = None
    failure: str | None = None

    @field_validator("token", "cursor", "state", "topic", "source", "target", "failure", mode="before")
    @classmethod
    def validate_strings(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("diagnostics request fields must be strings")
        return _non_blank_identifier(value)


class BrokerDiagnosticsDetail(BrokerWireModel):
    """Authenticate and request one redacted retained-event timeline."""

    type: Literal["broker.diagnostics.detail"] = "broker.diagnostics.detail"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    token: str
    event_id: str

    @field_validator("token", "event_id", mode="before")
    @classmethod
    def validate_identifiers(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("diagnostics detail fields must be strings")
        return _non_blank_identifier(value)


class BrokerDiagnosticsStatusResult(BrokerWireModel):
    """Read-only bounded-retention broker status without business data."""

    type: Literal["broker.diagnostics.status.result"] = "broker.diagnostics.status.result"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    generation: int = Field(ge=1)
    active_events: int = Field(ge=0)
    terminal_events: int = Field(ge=0)
    active_capacity: int = Field(ge=1)
    terminal_capacity: int = Field(ge=1)
    terminal_ttl_seconds: float = Field(gt=0)
    sessions: tuple[str, ...] = ()


class BrokerDiagnosticsEventRow(BrokerWireModel):
    """One redacted delivery-ledger row suitable for a local operator view."""

    event_id: str
    status: Literal["active", "settled"]
    topic: str
    source_bridge_id: str
    source_event_id: str
    ordering_key: str
    delivery_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    targets: tuple[str, ...] = ()
    failure_codes: tuple[str, ...] = ()


class BrokerDiagnosticsTransition(BrokerWireModel):
    """One redacted immutable event lifecycle transition."""

    order: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)
    kind: str
    target_bridge_id: str | None = None
    state: str | None = None
    success: bool | None = None
    failure_code: str | None = None


class BrokerDiagnosticsDetailResult(BrokerWireModel):
    """A redacted retained event with its bounded lifecycle timeline."""

    type: Literal["broker.diagnostics.detail.result"] = "broker.diagnostics.detail.result"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    event: BrokerDiagnosticsEventRow
    transitions: tuple[BrokerDiagnosticsTransition, ...] = ()


class BrokerDiagnosticsListResult(BrokerWireModel):
    """One opaque-cursor page of redacted retained broker events."""

    type: Literal["broker.diagnostics.list.result"] = "broker.diagnostics.list.result"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    events: tuple[BrokerDiagnosticsEventRow, ...] = ()
    next_cursor: str | None = None


type BrokerWireMessage = Annotated[
    BridgeRegister
    | BridgeRegistered
    | BridgeRejected
    | BridgeUnregister
    | BridgeUnregistered
    | BrokerDiagnosticsStatus
    | BrokerDiagnosticsList
    | BrokerDiagnosticsDetail
    | BrokerDiagnosticsStatusResult
    | BrokerDiagnosticsListResult
    | BrokerDiagnosticsDetailResult,
    Field(discriminator="type"),
]
BROKER_WIRE_ADAPTER: Final[TypeAdapter[BrokerWireMessage]] = TypeAdapter(BrokerWireMessage)

_TYPE_IDS: Final[dict[type[BrokerWireModel], int]] = {
    BridgeRegister: BROKER_REGISTER_TYPE_ID,
    BridgeRegistered: BROKER_REGISTERED_TYPE_ID,
    BridgeRejected: BROKER_REJECTED_TYPE_ID,
    BridgeUnregister: BROKER_UNREGISTER_TYPE_ID,
    BridgeUnregistered: BROKER_UNREGISTERED_TYPE_ID,
    BrokerDiagnosticsStatus: BROKER_DIAGNOSTICS_STATUS_TYPE_ID,
    BrokerDiagnosticsList: BROKER_DIAGNOSTICS_LIST_TYPE_ID,
    BrokerDiagnosticsDetail: BROKER_DIAGNOSTICS_DETAIL_TYPE_ID,
    BrokerDiagnosticsStatusResult: BROKER_DIAGNOSTICS_STATUS_RESULT_TYPE_ID,
    BrokerDiagnosticsListResult: BROKER_DIAGNOSTICS_LIST_RESULT_TYPE_ID,
    BrokerDiagnosticsDetailResult: BROKER_DIAGNOSTICS_DETAIL_RESULT_TYPE_ID,
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
