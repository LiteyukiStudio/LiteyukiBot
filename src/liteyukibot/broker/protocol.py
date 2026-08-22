"""Version 7 broker bridge-registration messages carried by LYIP frames."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Annotated, Final, Literal

from jsonschema import Draft202012Validator, SchemaError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_serializer, model_validator

from ..lyip import LyipError, LyipFrame, LyipLane
from ..topic_patterns import validate_topic_pattern

BROKER_PROTOCOL_VERSION: Final = 7
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
BROKER_LIFECYCLE_FREEZE_TYPE_ID: Final = 611
BROKER_LIFECYCLE_DRAIN_TYPE_ID: Final = 612
BROKER_LIFECYCLE_UNFREEZE_TYPE_ID: Final = 613
BROKER_LIFECYCLE_STATUS_RESULT_TYPE_ID: Final = 614


class BrokerWireError(LyipError):
    """Raised when a LYIP frame does not carry a valid broker v7 message."""


class BridgeAccess(StrEnum):
    """Enumerate the supported bridge access values."""
    FULL = "full"
    LIMITED = "limited"


class BrokerWireModel(BaseModel):
    """Represent the validated broker wire model contract."""
    model_config = ConfigDict(extra="forbid", frozen=True)


def _non_blank_identifier(value: str) -> str:
    """Implement the non blank identifier operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_non_blank_identifier`. It delegates to `strip` while
        keeping intermediate state local to the owning operation.
    """
    normalized = value.strip()
    if not normalized:
        raise ValueError("identifier must be non-empty")
    return normalized


def runtime_version_matches(requested: str, offered: str) -> bool:
    """Match the bounded runtime API caret range syntax.

    Args:
        requested: The requested value used by the operation.
        offered: The offered value used by the operation.

    Returns:
        Whether the requested condition is satisfied.
    """

    if requested == offered:
        return True
    if not requested.startswith("^"):
        return False
    raw_requested = requested[1:].split(".")
    raw_offered = offered.split(".")
    if len(raw_requested) < 2 or len(raw_offered) < 2:
        return False
    try:
        requested_major, requested_minor = int(raw_requested[0]), int(raw_requested[1])
        offered_major, offered_minor = int(raw_offered[0]), int(raw_offered[1])
    except ValueError:
        return False
    return offered_major == requested_major and offered_minor >= requested_minor


class ActionResourceDeclaration(BrokerWireModel):
    """An action kind and exact or prefix resource owned by one bridge."""

    kind: str
    resource: str | None = None
    resource_prefix: str | None = None

    @field_validator("kind", "resource", "resource_prefix", mode="before")
    @classmethod
    def validate_identifier(cls, value: object) -> str | None:
        """Validate identifier.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str | None` result produced by the operation.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("action resource fields must be strings")
        return _non_blank_identifier(value)

    @model_validator(mode="after")
    def validate_match_mode(self) -> ActionResourceDeclaration:
        """Validate match mode.

        Returns:
            The `ActionResourceDeclaration` result produced by the operation.
        """
        if (self.resource is None) == (self.resource_prefix is None):
            raise ValueError("action resource declarations must define exactly one of resource or resource_prefix")
        return self

    @model_serializer
    def serialize(self) -> dict[str, str]:
        """Implement the serialize operation for the action resource declaration.

        Returns:
            The `dict[str, str]` result produced by the operation.
        """
        result = {"kind": self.kind}
        if self.resource is not None:
            result["resource"] = self.resource
        if self.resource_prefix is not None:
            result["resource_prefix"] = self.resource_prefix
        return result

    def matches(self, resource_key: str) -> bool:
        """Return whether this declaration owns the supplied resource key.

        Args:
            resource_key: The resource key value used by the operation.

        Returns:
            Whether the requested condition is satisfied.
        """

        if self.resource is not None:
            return resource_key == self.resource
        assert self.resource_prefix is not None
        return resource_key.startswith(self.resource_prefix)

    @property
    def is_exact(self) -> bool:
        """Return the action resource declaration's is exact.

        Returns:
            Whether the requested condition is satisfied.
        """
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
        """Validate text.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("tool declaration fields must be strings")
        return _non_blank_identifier(value)

    @field_validator("capabilities", mode="before")
    @classmethod
    def validate_capabilities(cls, value: object) -> tuple[str, ...]:
        """Validate capabilities.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if not isinstance(value, (list, tuple)):
            raise TypeError("tool capabilities must be an array")
        result = tuple(_non_blank_identifier(item) for item in value if isinstance(item, str))
        if len(result) != len(value) or len(result) != len(set(result)):
            raise ValueError("tool capabilities must be unique strings")
        return result


class RuntimeApiDeclaration(BrokerWireModel):
    """One immutable operation exposed by a runtime bridge."""

    runtime_kind: str
    namespace: str
    operation: str
    version: str
    input_schema: Mapping[str, object]
    output_schema: Mapping[str, object]
    capabilities: tuple[str, ...] = ()

    @field_validator("runtime_kind", "namespace", "operation", "version", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        """Validate text.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("runtime API declaration fields must be strings")
        return _non_blank_identifier(value)

    @field_validator("capabilities", mode="before")
    @classmethod
    def validate_capabilities(cls, value: object) -> tuple[str, ...]:
        """Validate capabilities.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if not isinstance(value, (list, tuple)):
            raise TypeError("runtime API capabilities must be an array")
        result = tuple(_non_blank_identifier(item) for item in value if isinstance(item, str))
        if len(result) != len(value) or len(result) != len(set(result)):
            raise ValueError("runtime API capabilities must be unique strings")
        return result

    @field_validator("input_schema", "output_schema")
    @classmethod
    def validate_schema(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        """Validate schema.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, object]` result produced by the operation.
        """
        try:
            Draft202012Validator.check_schema(dict(value))
        except SchemaError as error:
            raise ValueError("runtime API schema must be Draft 2020-12 compatible") from error
        return dict(value)

    @property
    def api_id(self) -> str:
        """Return the runtime api declaration's api id.

        Returns:
            The `str` result produced by the operation.
        """
        return f"{self.namespace}.{self.operation}"


def runtime_api_catalog_fingerprint(declarations: Sequence[RuntimeApiDeclaration]) -> str:
    """Return a deterministic digest for one runtime API catalog.

    Args:
        declarations: The declarations value used by the operation.

    Returns:
        The `str` result produced by the operation.
    """

    serialized = [declaration.model_dump(mode="json") for declaration in declarations]
    serialized.sort(
        key=lambda value: tuple(
            str(value[field]) for field in ("runtime_kind", "namespace", "operation", "version")
        )
    )
    payload = json.dumps(serialized, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class AuthorizationContextWire(BrokerWireModel):
    """Only event identity and principal fields may cross the Tool wire."""

    event_id: str
    runtime_id: str
    bot_id: str
    actor_id: str | None = None

    @field_validator("event_id", "runtime_id", "bot_id", "actor_id", mode="before")
    @classmethod
    def validate_context_text(cls, value: object) -> str | None:
        """Validate context text.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str | None` result produced by the operation.
        """
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
    controls: tuple[str, ...] = ()
    runtime_apis: tuple[RuntimeApiDeclaration, ...] = ()
    runtime_api_fingerprint: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )

    @field_validator("bridge_id", mode="before")
    @classmethod
    def validate_bridge_id(cls, value: object) -> str:
        """Validate bridge id.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("bridge identifier must be a string")
        return _non_blank_identifier(value)

    @field_validator("subscriptions", mode="before")
    @classmethod
    def validate_declarations(cls, value: object) -> tuple[str, ...]:
        """Validate declarations.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if not isinstance(value, (list, tuple)):
            raise TypeError("bridge declarations must be a JSON array")
        declarations: list[str] = []
        for declaration in value:
            declarations.append(validate_topic_pattern(declaration, subject="bridge declaration"))
        if len(declarations) != len(set(declarations)):
            raise ValueError("bridge declarations must not contain duplicates")
        return tuple(declarations)

    @field_validator("controls", mode="before")
    @classmethod
    def validate_controls(cls, value: object) -> tuple[str, ...]:
        """Validate controls.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if not isinstance(value, (list, tuple)):
            raise TypeError("bridge controls must be a JSON array")
        controls = tuple(_non_blank_identifier(item) for item in value if isinstance(item, str))
        if len(controls) != len(value) or len(controls) != len(set(controls)):
            raise ValueError("bridge controls must be unique strings")
        return controls

    @model_validator(mode="after")
    def validate_action_resources(self) -> BridgeManifest:
        """Validate action resources.

        Returns:
            The `BridgeManifest` result produced by the operation.
        """
        keys = tuple(
            (resource.kind, resource.resource, resource.resource_prefix) for resource in self.action_resources
        )
        if len(set(keys)) != len(self.action_resources):
            raise ValueError("action resources must not contain duplicates")
        tool_ids = tuple(tool.id for tool in self.tools)
        if len(tool_ids) != len(set(tool_ids)):
            raise ValueError("tool declarations must not contain duplicate IDs")
        api_ids = tuple((api.runtime_kind, api.api_id) for api in self.runtime_apis)
        if len(api_ids) != len(set(api_ids)):
            raise ValueError("runtime API declarations must not contain duplicate IDs")
        if self.runtime_apis:
            expected_fingerprint = runtime_api_catalog_fingerprint(self.runtime_apis)
            if self.runtime_api_fingerprint is None:
                object.__setattr__(self, "runtime_api_fingerprint", expected_fingerprint)
            elif self.runtime_api_fingerprint != expected_fingerprint:
                raise ValueError("runtime API catalog fingerprint does not match its declarations")
        elif self.runtime_api_fingerprint is not None:
            raise ValueError("runtime API catalog fingerprint requires runtime API declarations")
        return self


class BridgeRegister(BrokerWireModel):
    """Represent the validated bridge register contract."""
    type: Literal["bridge.register"] = "bridge.register"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    bridge_id: str
    instance_token: str
    manifest: BridgeManifest

    @field_validator("bridge_id", "instance_token", mode="before")
    @classmethod
    def validate_identifiers(cls, value: object) -> str:
        """Validate identifiers.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("bridge registration fields must be strings")
        return _non_blank_identifier(value)

    @model_validator(mode="after")
    def validate_manifest_bridge(self) -> BridgeRegister:
        """Validate manifest bridge.

        Returns:
            The `BridgeRegister` result produced by the operation.
        """
        if self.bridge_id != self.manifest.bridge_id:
            raise ValueError("registration bridge identifier must match manifest")
        return self


class BridgeRegistered(BrokerWireModel):
    """Represent the validated bridge registered contract."""
    type: Literal["bridge.registered"] = "bridge.registered"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    session_id: str

    @field_validator("session_id", mode="before")
    @classmethod
    def validate_session_id(cls, value: object) -> str:
        """Validate session id.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("session identifier must be a string")
        return _non_blank_identifier(value)


class BridgeRejected(BrokerWireModel):
    """Represent the validated bridge rejected contract."""
    type: Literal["bridge.rejected"] = "bridge.rejected"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    code: str
    message: str

    @field_validator("code", "message", mode="before")
    @classmethod
    def validate_rejection_fields(cls, value: object) -> str:
        """Validate rejection fields.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("rejection fields must be strings")
        return _non_blank_identifier(value)


class BridgeUnregister(BrokerWireModel):
    """Represent the validated bridge unregister contract."""
    type: Literal["bridge.unregister"] = "bridge.unregister"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    session_id: str

    @field_validator("session_id", mode="before")
    @classmethod
    def validate_session_id(cls, value: object) -> str:
        """Validate session id.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("session identifier must be a string")
        return _non_blank_identifier(value)


class BridgeUnregistered(BrokerWireModel):
    """Represent the validated bridge unregistered contract."""
    type: Literal["bridge.unregistered"] = "bridge.unregistered"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    session_id: str

    @field_validator("session_id", mode="before")
    @classmethod
    def validate_session_id(cls, value: object) -> str:
        """Validate session id.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("session identifier must be a string")
        return _non_blank_identifier(value)


class BrokerDiagnosticsStatus(BrokerWireModel):
    """Authenticate and request bounded broker diagnostic status."""

    type: Literal["broker.diagnostics.status"] = "broker.diagnostics.status"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    token: str

    @field_validator("token", mode="before")
    @classmethod
    def validate_token(cls, value: object) -> str:
        """Validate token.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("diagnostics token must be a string")
        return _non_blank_identifier(value)


class BrokerDiagnosticsList(BrokerWireModel):
    """Authenticate and request one redacted event-delivery page."""

    type: Literal["broker.diagnostics.list"] = "broker.diagnostics.list"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
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
        """Validate strings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str | None` result produced by the operation.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("diagnostics request fields must be strings")
        return _non_blank_identifier(value)


class BrokerDiagnosticsDetail(BrokerWireModel):
    """Authenticate and request one redacted retained-event timeline."""

    type: Literal["broker.diagnostics.detail"] = "broker.diagnostics.detail"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    token: str
    event_id: str

    @field_validator("token", "event_id", mode="before")
    @classmethod
    def validate_identifiers(cls, value: object) -> str:
        """Validate identifiers.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("diagnostics detail fields must be strings")
        return _non_blank_identifier(value)


class BrokerDiagnosticsStatusResult(BrokerWireModel):
    """Read-only bounded-retention broker status without business data."""

    type: Literal["broker.diagnostics.status.result"] = "broker.diagnostics.status.result"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    generation: int = Field(ge=1)
    active_events: int = Field(ge=0)
    terminal_events: int = Field(ge=0)
    active_capacity: int = Field(ge=1)
    terminal_capacity: int = Field(ge=1)
    terminal_content_bytes: int = Field(ge=0)
    terminal_content_bytes_capacity: int = Field(ge=1)
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
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    event: BrokerDiagnosticsEventRow
    transitions: tuple[BrokerDiagnosticsTransition, ...] = ()


class BrokerDiagnosticsListResult(BrokerWireModel):
    """One opaque-cursor page of redacted retained broker events."""

    type: Literal["broker.diagnostics.list.result"] = "broker.diagnostics.list.result"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    events: tuple[BrokerDiagnosticsEventRow, ...] = ()
    next_cursor: str | None = None


class BrokerLifecycleFreeze(BrokerWireModel):
    """Authenticate and stop admitting new business events."""

    type: Literal["broker.lifecycle.freeze"] = "broker.lifecycle.freeze"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    token: str
    reason: str = "instance update"

    @field_validator("token", "reason", mode="before")
    @classmethod
    def validate_lifecycle_text(cls, value: object) -> str:
        """Validate lifecycle text.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("broker lifecycle fields must be strings")
        return _non_blank_identifier(value)


class BrokerLifecycleDrain(BrokerWireModel):
    """Authenticate and request the current bounded drain status."""

    type: Literal["broker.lifecycle.drain"] = "broker.lifecycle.drain"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    token: str

    @field_validator("token", mode="before")
    @classmethod
    def validate_token(cls, value: object) -> str:
        """Validate token.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("broker management token must be a string")
        return _non_blank_identifier(value)


class BrokerLifecycleUnfreeze(BrokerWireModel):
    """Authenticate and restore business admission after an aborted update."""

    type: Literal["broker.lifecycle.unfreeze"] = "broker.lifecycle.unfreeze"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    token: str

    @field_validator("token", mode="before")
    @classmethod
    def validate_token(cls, value: object) -> str:
        """Validate token.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not isinstance(value, str):
            raise TypeError("broker management token must be a string")
        return _non_blank_identifier(value)


class BrokerLifecycleStatusResult(BrokerWireModel):
    """Bounded state returned to the daemon update coordinator."""

    type: Literal["broker.lifecycle.status.result"] = "broker.lifecycle.status.result"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    frozen: bool
    reason: str | None = None
    active_events: int = Field(ge=0)
    sessions: tuple[str, ...] = ()


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
    | BrokerDiagnosticsDetailResult
    | BrokerLifecycleFreeze
    | BrokerLifecycleDrain
    | BrokerLifecycleUnfreeze
    | BrokerLifecycleStatusResult,
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
    BrokerLifecycleFreeze: BROKER_LIFECYCLE_FREEZE_TYPE_ID,
    BrokerLifecycleDrain: BROKER_LIFECYCLE_DRAIN_TYPE_ID,
    BrokerLifecycleUnfreeze: BROKER_LIFECYCLE_UNFREEZE_TYPE_ID,
    BrokerLifecycleStatusResult: BROKER_LIFECYCLE_STATUS_RESULT_TYPE_ID,
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
    """Encode one v7 control-plane message into an existing LYIP frame.

    Args:
        message: Message content associated with the operation.
        generation: Positive protocol or deployment generation.
        stream_id: Stable identifier for the stream.
        sequence: Monotonic sequence number for the stream.
        lease_id: Stable identifier for the lease.

    Returns:
        The `LyipFrame` result produced by the operation.
    """

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
    """Decode a v7 broker control message without accepting legacy runtime types.

    Args:
        frame: The frame value used by the operation.

    Returns:
        The `BrokerWireMessage` result produced by the operation.
    """

    if frame.lane is not LyipLane.CONTROL:
        raise BrokerWireError("broker control message arrived on the wrong LYIP lane")
    message_type = _MESSAGE_TYPES.get(frame.type_id)
    if message_type is None:
        raise BrokerWireError(f"unknown broker v7 type ID: {frame.type_id}")
    try:
        message = message_type.model_validate_json(frame.payload)
    except ValueError as error:
        raise BrokerWireError("broker v7 payload is invalid") from error
    if _TYPE_IDS[type(message)] != frame.type_id:
        raise BrokerWireError("broker v7 type ID does not match payload type")
    return message  # type: ignore[return-value]
