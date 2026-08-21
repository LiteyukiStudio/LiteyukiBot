"""Broker-owned, bounded event delivery and portable action routing."""

from __future__ import annotations

import json
import secrets
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from ..events.models import JsonValue
from ..topic_patterns import topic_pattern_matches
from .peer import BridgeRegistrationError, BridgeSession
from .protocol import BROKER_PROTOCOL_VERSION, AuthorizationContextWire, BridgeAccess, runtime_version_matches


def _validate_json(value: Any, path: str = "payload") -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{path} must not contain NaN or infinity")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} must use string object keys")
            _validate_json(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_json(item, f"{path}[{index}]")
        return
    raise ValueError(f"{path} contains non-JSON value {type(value).__name__}")


def _freeze(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: JsonValue) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


class BrokerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, validate_default=True)


class EventIngress(BrokerModel):
    """The only event shape accepted from a bridge business lane."""

    type: Literal["event.ingress"] = "event.ingress"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    source_event_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    ordering_key: str = Field(min_length=1)
    payload: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload(cls, value: Any) -> Any:
        _validate_json(value)
        return value

    @field_validator("payload", mode="after")
    @classmethod
    def freeze_payload(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})

    @field_serializer("payload")
    def serialize_payload(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return {key: _thaw(item) for key, item in value.items()}


class BrokerEvent(BrokerModel):
    """Immutable broker-created event identity and authenticated provenance."""

    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    kernel_event_id: str = Field(min_length=1)
    source_bridge_id: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    ordering_key: str = Field(min_length=1)
    payload: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload(cls, value: Any) -> Any:
        _validate_json(value)
        return value

    @field_validator("payload", mode="after")
    @classmethod
    def freeze_payload(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})

    @field_serializer("payload")
    def serialize_payload(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return {key: _thaw(item) for key, item in value.items()}


class DeliveryState(StrEnum):
    PENDING = "pending"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


_TERMINAL_STATES = frozenset({DeliveryState.COMPLETED, DeliveryState.FAILED, DeliveryState.EXPIRED})


class ActionRequest(BrokerModel):
    type: Literal["action.request"] = "action.request"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    delivery_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    resource_key: str = Field(min_length=1)
    payload: Mapping[str, JsonValue] = Field(default_factory=dict)
    action_id: str | None = Field(default=None, min_length=1)

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload(cls, value: Any) -> Any:
        _validate_json(value)
        return value

    @field_validator("payload", mode="after")
    @classmethod
    def freeze_payload(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})

    @field_serializer("payload")
    def serialize_payload(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return {key: _thaw(item) for key, item in value.items()}


class EventMessage(BrokerModel):
    """Broker-to-bridge event delivery carrying an opaque broker lease."""

    type: Literal["event.message"] = "event.message"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    delivery_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    lease_ttl_ms: int = Field(ge=1)
    attempt: Literal[1] = 1
    event: BrokerEvent


class EventAccepted(BrokerModel):
    """Bridge acknowledgement that transitions an offered delivery to active."""

    type: Literal["event.accepted"] = "event.accepted"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    delivery_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)


class EventCompleted(BrokerModel):
    """Terminal outcome of an active broker event delivery."""

    type: Literal["event.completed"] = "event.completed"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    delivery_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    success: bool
    failure_reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.success and self.failure_reason is not None:
            raise ValueError("successful event completions cannot contain failure_reason")
        if not self.success and self.failure_reason is None:
            raise ValueError("failed event completions require failure_reason")
        return self


class ActionResult(BrokerModel):
    """Terminal result returned by the bridge selected for one action."""

    type: Literal["action.result"] = "action.result"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    action_id: str = Field(min_length=1)
    # The owner omits this field. The broker fills it from the retained request
    # before forwarding the result to its origin bridge.
    correlation_id: str | None = Field(default=None, min_length=1)
    success: bool
    payload: JsonValue = None

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload(cls, value: Any) -> Any:
        _validate_json(value, "action result")
        return value

    @field_validator("payload", mode="after")
    @classmethod
    def freeze_payload(cls, value: JsonValue) -> JsonValue:
        return _freeze(value)

    @field_serializer("payload")
    def serialize_payload(self, value: JsonValue) -> Any:
        return _thaw(value)


class ToolInvoke(BrokerModel):
    """A lease-bound Tool invocation sent by a caller bridge."""

    type: Literal["tool.invoke"] = "tool.invoke"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    delivery_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    tool_id: str = Field(min_length=1)
    arguments: Mapping[str, JsonValue] = Field(default_factory=dict)
    authorization: AuthorizationContextWire
    invocation_id: str | None = Field(default=None, min_length=1)

    @field_validator("arguments", mode="before")
    @classmethod
    def validate_arguments(cls, value: Any) -> Any:
        _validate_json(value, "tool arguments")
        return value

    @field_validator("arguments", mode="after")
    @classmethod
    def freeze_arguments(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})

    @field_serializer("arguments")
    def serialize_arguments(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return {key: _thaw(item) for key, item in value.items()}


class ToolResult(BrokerModel):
    """Stable, redacted result returned by a Tool provider."""

    type: Literal["tool.result"] = "tool.result"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    invocation_id: str = Field(min_length=1)
    correlation_id: str | None = Field(default=None, min_length=1)
    success: bool
    result: JsonValue = None
    error_code: str | None = Field(default=None, min_length=1)
    error_details: Mapping[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_result(self) -> ToolResult:
        if self.success and self.error_code is not None:
            raise ValueError("successful Tool results cannot contain an error code")
        if not self.success and self.error_code is None:
            raise ValueError("failed Tool results require a stable error code")
        _validate_json(self.result, "tool result")
        if self.error_details is not None:
            _validate_json(self.error_details, "tool error details")
        return self


class RuntimeApiInvoke(BrokerModel):
    """A lease-bound runtime API invocation sent by a caller bridge."""

    type: Literal["runtime.api.invoke"] = "runtime.api.invoke"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    delivery_id: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    runtime_kind: str = Field(min_length=1)
    version: str = Field(min_length=1)
    bridge_id: str | None = Field(default=None, min_length=1)
    api_id: str = Field(min_length=1)
    caller_extension_id: str = Field(min_length=1)
    arguments: Mapping[str, JsonValue] = Field(default_factory=dict)
    authorization: AuthorizationContextWire
    invocation_id: str | None = Field(default=None, min_length=1)

    @field_validator(
        "source_event_id", "runtime_kind", "version", "api_id", "caller_extension_id", "bridge_id", mode="before"
    )
    @classmethod
    def validate_identifiers(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise TypeError("runtime API identifiers must be non-empty strings")
        return value.strip()

    @field_validator("arguments", mode="before")
    @classmethod
    def validate_arguments(cls, value: Any) -> Any:
        _validate_json(value, "runtime API arguments")
        return value

    @field_validator("arguments", mode="after")
    @classmethod
    def freeze_arguments(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})

    @field_serializer("arguments")
    def serialize_arguments(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return {key: _thaw(item) for key, item in value.items()}


class RuntimeApiResult(BrokerModel):
    """Stable result returned by a runtime API provider."""

    type: Literal["runtime.api.result"] = "runtime.api.result"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    invocation_id: str = Field(min_length=1)
    correlation_id: str | None = Field(default=None, min_length=1)
    success: bool
    result: JsonValue = None
    error_code: str | None = Field(default=None, min_length=1)
    error_details: Mapping[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_result(self) -> RuntimeApiResult:
        if self.success and self.error_code is not None:
            raise ValueError("successful runtime API results cannot contain an error code")
        if not self.success and self.error_code is None:
            raise ValueError("failed runtime API results require a stable error code")
        _validate_json(self.result, "runtime API result")
        if self.error_details is not None:
            _validate_json(self.error_details, "runtime API error details")
        return self


class BridgeControlInvoke(BrokerModel):
    """A lease-bound control invocation sent by a caller bridge."""

    type: Literal["bridge.control.invoke"] = "bridge.control.invoke"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    delivery_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    command: str = Field(min_length=1)
    authorization: AuthorizationContextWire
    payload: Mapping[str, JsonValue] = Field(default_factory=dict)
    invocation_id: str | None = Field(default=None, min_length=1)

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload(cls, value: Any) -> Any:
        _validate_json(value, "control payload")
        return value

    @field_validator("payload", mode="after")
    @classmethod
    def freeze_payload(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})

    @field_serializer("payload")
    def serialize_payload(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return {key: _thaw(item) for key, item in value.items()}


class BridgeControlResult(BrokerModel):
    """Stable result returned by a bridge control owner."""

    type: Literal["bridge.control.result"] = "bridge.control.result"
    protocol: Literal[7] = BROKER_PROTOCOL_VERSION
    invocation_id: str = Field(min_length=1)
    correlation_id: str | None = Field(default=None, min_length=1)
    success: bool
    result: JsonValue = None
    error_code: str | None = Field(default=None, min_length=1)
    error_details: Mapping[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_result(self) -> BridgeControlResult:
        if self.success and self.error_code is not None:
            raise ValueError("successful bridge control results cannot contain an error code")
        if not self.success and self.error_code is None:
            raise ValueError("failed bridge control results require a stable error code")
        _validate_json(self.result, "control result")
        if self.error_details is not None:
            _validate_json(self.error_details, "control error details")
        return self


@dataclass(frozen=True, slots=True)
class RoutedAction:
    action_id: str
    event_id: str
    request: ActionRequest
    target: BridgeSession
    origin: BridgeSession
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class RoutedControl:
    invocation_id: str
    event_id: str
    request: BridgeControlInvoke
    target: BridgeSession
    origin: BridgeSession
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class RoutedRuntimeApi:
    invocation_id: str
    event_id: str
    request: RuntimeApiInvoke
    target: BridgeSession
    origin: BridgeSession
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class DeliverySnapshot:
    delivery_id: str
    target_bridge_id: str
    state: DeliveryState
    attempt: Literal[1]
    lease_id: str
    lease_ttl_ms: int
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class EventSnapshot:
    event: BrokerEvent
    status: Literal["active", "settled"]
    deliveries: tuple[DeliverySnapshot, ...]
    failure_count: int
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LedgerTransition:
    """Internal bounded lifecycle evidence consumed only by diagnostics projection."""

    order: int
    elapsed_ms: int
    kind: str
    target_bridge_id: str | None = None
    state: DeliveryState | None = None
    success: bool | None = None
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class LedgerDiagnosticSnapshot:
    """Retained raw ledger state for the broker-local redaction projection."""

    event: BrokerEvent
    status: Literal["active", "settled"]
    deliveries: tuple[DeliverySnapshot, ...]
    transitions: tuple[LedgerTransition, ...]


@dataclass(slots=True)
class _Delivery:
    delivery_id: str
    event_id: str
    target_bridge_id: str
    lane: tuple[str, str, str]
    state: DeliveryState = DeliveryState.PENDING
    lease_id: str = ""
    lease_deadline: float | None = None
    failure_reason: str | None = None


@dataclass(slots=True)
class _Action:
    routed: RoutedAction
    canonical_request: str
    result: ActionResult | None = None


@dataclass(slots=True)
class _Tool:
    routed: RoutedTool
    canonical_request: str
    result: ToolResult | None = None


@dataclass(slots=True)
class _Control:
    routed: RoutedControl
    canonical_request: str
    result: BridgeControlResult | None = None


@dataclass(slots=True)
class _RuntimeApi:
    routed: RoutedRuntimeApi
    canonical_request: str
    result: RuntimeApiResult | None = None


@dataclass(frozen=True, slots=True)
class RoutedTool:
    invocation_id: str
    event_id: str
    request: ToolInvoke
    target: BridgeSession
    origin: BridgeSession
    replayed: bool = False


@dataclass(slots=True)
class _EventRecord:
    event: BrokerEvent
    admitted_at: float
    deliveries: dict[str, _Delivery] = field(default_factory=dict)
    actions: dict[tuple[str, str], _Action] = field(default_factory=dict)
    tools: dict[tuple[str, str], _Tool] = field(default_factory=dict)
    controls: dict[tuple[str, str], _Control] = field(default_factory=dict)
    runtime_apis: dict[tuple[str, str], _RuntimeApi] = field(default_factory=dict)
    transitions: list[LedgerTransition] = field(default_factory=list)
    terminal_at: float | None = None


class BrokerAdmissionError(BridgeRegistrationError):
    """Raised when an authenticated bridge violates the broker business contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BrokerLedger:
    """Bounded event ledger; all deadlines are evaluated by the broker clock."""

    def __init__(
        self,
        *,
        active_capacity: int = 1024,
        terminal_capacity: int = 16384,
        terminal_ttl_seconds: float = 3600.0,
        delivery_timeout_seconds: float = 30.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if active_capacity < 1 or terminal_capacity < 1:
            raise ValueError("broker event capacities must be positive")
        if terminal_ttl_seconds <= 0 or delivery_timeout_seconds <= 0:
            raise ValueError("broker retention and delivery timeouts must be positive")
        self.active_capacity = active_capacity
        self.terminal_capacity = terminal_capacity
        self.terminal_ttl_seconds = terminal_ttl_seconds
        self.delivery_timeout_seconds = delivery_timeout_seconds
        self._monotonic = monotonic
        self._active: dict[str, _EventRecord] = {}
        self._active_order: deque[str] = deque()
        self._terminal: dict[str, _EventRecord] = {}
        self._terminal_order: deque[str] = deque()
        self._delivery_index: dict[str, _EventRecord] = {}
        self._action_index: dict[str, _Action] = {}
        self._tool_index: dict[str, _Tool] = {}
        self._control_index: dict[str, _Control] = {}
        self._runtime_api_index: dict[str, _RuntimeApi] = {}
        self._lanes: dict[tuple[str, str, str], deque[str]] = {}

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def terminal_count(self) -> int:
        self.expire()
        return len(self._terminal)

    def index_counts(self) -> tuple[int, int]:
        """Expose bounded internal index sizes for deterministic contract tests."""

        self.expire()
        return len(self._delivery_index), len(self._lanes)

    def diagnostic_snapshots(self) -> tuple[LedgerDiagnosticSnapshot, ...]:
        """Return currently retained raw records for broker-local diagnostics only."""

        self.expire()
        event_ids = tuple(reversed(self._active_order)) + tuple(reversed(self._terminal_order))
        records = tuple((self._active.get(event_id) or self._terminal.get(event_id)) for event_id in event_ids)
        return tuple(
            LedgerDiagnosticSnapshot(
                event=record.event,
                status="settled" if record.terminal_at is not None else "active",
                deliveries=tuple(self._snapshot_delivery(delivery) for delivery in record.deliveries.values()),
                transitions=tuple(record.transitions),
            )
            for record in records
            if record is not None
        )

    def admit_event(
        self,
        session: BridgeSession,
        ingress: EventIngress,
        sessions: tuple[BridgeSession, ...],
    ) -> BrokerEvent:
        self.expire()
        if self.active_count >= self.active_capacity:
            raise BrokerAdmissionError("active_capacity", "broker active event capacity is exhausted")
        event = BrokerEvent(
            kernel_event_id=str(uuid4()),
            source_bridge_id=session.bridge_id,
            source_event_id=ingress.source_event_id,
            topic=ingress.topic,
            ordering_key=ingress.ordering_key,
            payload=ingress.payload,
        )
        record = _EventRecord(event=event, admitted_at=self._monotonic())
        self._record_transition(record, "event.admitted")
        self._active[event.kernel_event_id] = record
        self._active_order.append(event.kernel_event_id)
        for target in self.event_subscribers(event, sessions):
            delivery_id = str(uuid4())
            lane = (session.bridge_id, ingress.ordering_key, target.bridge_id)
            delivery = _Delivery(delivery_id, event.kernel_event_id, target.bridge_id, lane)
            record.deliveries[delivery_id] = delivery
            self._record_transition(
                record,
                "delivery.pending",
                target_bridge_id=target.bridge_id,
                state=DeliveryState.PENDING,
            )
            self._delivery_index[delivery_id] = record
            self._lanes.setdefault(lane, deque()).append(delivery_id)
        if not record.deliveries:
            self._settle(record)
        else:
            for delivery in record.deliveries.values():
                self._offer_next(delivery.lane)
        return event

    def event_snapshot(self, event_id: str) -> EventSnapshot:
        self.expire()
        record = self._active.get(event_id) or self._terminal.get(event_id)
        if record is None:
            raise BrokerAdmissionError("unknown_event", "broker event is not retained")
        failures = tuple(
            delivery.failure_reason for delivery in record.deliveries.values() if delivery.failure_reason is not None
        )
        return EventSnapshot(
            event=record.event,
            status="settled" if record.terminal_at is not None else "active",
            deliveries=tuple(self._snapshot_delivery(delivery) for delivery in record.deliveries.values()),
            failure_count=len(failures),
            failure_reasons=failures,
        )

    def offered_deliveries(self, event_id: str) -> tuple[DeliverySnapshot, ...]:
        snapshot = self.event_snapshot(event_id)
        return tuple(delivery for delivery in snapshot.deliveries if delivery.state is DeliveryState.OFFERED)

    def accept_delivery(self, session: BridgeSession, delivery_id: str, lease_id: str) -> DeliverySnapshot:
        delivery = self._require_delivery(session, delivery_id, lease_id, DeliveryState.OFFERED)
        delivery.state = DeliveryState.ACCEPTED
        self._record_delivery_transition(delivery, "delivery.accepted")
        return self._snapshot_delivery(delivery)

    def activate_delivery(self, session: BridgeSession, delivery_id: str, lease_id: str) -> DeliverySnapshot:
        delivery = self._require_delivery(session, delivery_id, lease_id, DeliveryState.ACCEPTED)
        delivery.state = DeliveryState.ACTIVE
        self._record_delivery_transition(delivery, "delivery.active")
        return self._snapshot_delivery(delivery)

    def complete_delivery(
        self,
        session: BridgeSession,
        delivery_id: str,
        lease_id: str,
        *,
        success: bool,
        failure_reason: str | None = None,
    ) -> DeliverySnapshot:
        snapshot, _next_offer = self.complete_delivery_with_next_offer(
            session,
            delivery_id,
            lease_id,
            success=success,
            failure_reason=failure_reason,
        )
        return snapshot

    def complete_delivery_with_next_offer(
        self,
        session: BridgeSession,
        delivery_id: str,
        lease_id: str,
        *,
        success: bool,
        failure_reason: str | None = None,
    ) -> tuple[DeliverySnapshot, tuple[BrokerEvent, DeliverySnapshot] | None]:
        """Complete one delivery and reveal the next FIFO offer, if it became sendable."""

        delivery = self._require_delivery(session, delivery_id, lease_id, DeliveryState.ACTIVE)
        if success:
            delivery.state = DeliveryState.COMPLETED
        else:
            delivery.state = DeliveryState.FAILED
            delivery.failure_reason = failure_reason or "bridge_failed"
        self._record_delivery_transition(delivery, "delivery.completed", success=success)
        next_delivery = self._terminalize_delivery(delivery)
        next_offer = None
        if next_delivery is not None:
            next_record = self._delivery_index[next_delivery.delivery_id]
            next_offer = (next_record.event, self._snapshot_delivery(next_delivery))
        return self._snapshot_delivery(delivery), next_offer

    def route_action(
        self,
        session: BridgeSession,
        request: ActionRequest,
        sessions: tuple[BridgeSession, ...],
    ) -> RoutedAction:
        delivery = self._require_delivery(session, request.delivery_id, request.lease_id, DeliveryState.ACTIVE)
        record = self._delivery_index[delivery.delivery_id]
        canonical = json.dumps(
            request.model_dump(mode="json", by_alias=True, exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
        )
        key = (session.session_id, request.correlation_id)
        previous = record.actions.get(key)
        if previous is not None:
            if previous.canonical_request != canonical:
                raise BrokerAdmissionError("action_conflict", "correlation ID was already used with different content")
            return RoutedAction(
                action_id=previous.routed.action_id,
                event_id=previous.routed.event_id,
                request=previous.routed.request,
                target=previous.routed.target,
                origin=previous.routed.origin,
                replayed=True,
            )
        target = self._resolve_owner(request.kind, request.resource_key, sessions)
        routed = RoutedAction(str(uuid4()), record.event.kernel_event_id, request, target, session)
        record.actions[key] = _Action(routed=routed, canonical_request=canonical)
        self._action_index[routed.action_id] = record.actions[key]
        self._record_transition(record, "action.routed", target_bridge_id=target.bridge_id)
        return routed

    def route_tool(
        self, session: BridgeSession, request: ToolInvoke, sessions: tuple[BridgeSession, ...]
    ) -> RoutedTool:
        delivery = self._require_delivery(session, request.delivery_id, request.lease_id, DeliveryState.ACTIVE)
        record = self._delivery_index[delivery.delivery_id]
        canonical = json.dumps(
            request.model_dump(mode="json", exclude_none=True), sort_keys=True, separators=(",", ":")
        )
        key = (session.session_id, request.correlation_id)
        previous = record.tools.get(key)
        if previous is not None:
            if previous.canonical_request != canonical:
                raise BrokerAdmissionError(
                    "tool_conflict", "correlation ID was already used with different Tool content"
                )
            return RoutedTool(
                invocation_id=previous.routed.invocation_id,
                event_id=previous.routed.event_id,
                request=previous.routed.request,
                target=previous.routed.target,
                origin=previous.routed.origin,
                replayed=True,
            )
        owners = tuple(
            session for session in sessions if any(tool.id == request.tool_id for tool in session.manifest.tools)
        )
        if len(owners) != 1:
            raise BrokerAdmissionError(
                "tool_owner_conflict" if owners else "unknown_tool", "Tool ownership is not unique"
            )
        routed = RoutedTool(str(uuid4()), record.event.kernel_event_id, request, owners[0], session)
        record.tools[key] = _Tool(routed=routed, canonical_request=canonical)
        self._tool_index[routed.invocation_id] = record.tools[key]
        self._record_transition(record, "tool.routed", target_bridge_id=owners[0].bridge_id)
        return routed

    def route_control(
        self, session: BridgeSession, request: BridgeControlInvoke, sessions: tuple[BridgeSession, ...]
    ) -> RoutedControl:
        delivery = self._require_delivery(session, request.delivery_id, request.lease_id, DeliveryState.ACTIVE)
        record = self._delivery_index[delivery.delivery_id]
        authorization = request.authorization
        if authorization.event_id != record.event.kernel_event_id:
            raise BrokerAdmissionError(
                "control_authorization_mismatch",
                "control authorization does not match the routed event",
            )
        if authorization.runtime_id != record.event.source_bridge_id:
            raise BrokerAdmissionError(
                "control_authorization_mismatch",
                "control authorization runtime does not match the routed event",
            )
        event_payload = record.event.payload
        if isinstance(event_payload, Mapping):
            event_bot_id = event_payload.get("bot_id")
            if isinstance(event_bot_id, str) and authorization.bot_id != event_bot_id:
                raise BrokerAdmissionError(
                    "control_authorization_mismatch",
                    "control authorization bot does not match the routed event",
                )
            event_actor = event_payload.get("actor")
            if isinstance(event_actor, Mapping):
                event_actor_id = event_actor.get("id")
                if isinstance(event_actor_id, str) and authorization.actor_id != event_actor_id:
                    raise BrokerAdmissionError(
                        "control_authorization_mismatch",
                        "control authorization actor does not match the routed event",
                    )
        canonical = json.dumps(
            request.model_dump(mode="json", exclude_none=True), sort_keys=True, separators=(",", ":")
        )
        key = (session.session_id, request.correlation_id)
        previous = record.controls.get(key)
        if previous is not None:
            if previous.canonical_request != canonical:
                raise BrokerAdmissionError(
                    "control_conflict", "correlation ID was already used with different control content"
                )
            return RoutedControl(
                invocation_id=previous.routed.invocation_id,
                event_id=previous.routed.event_id,
                request=previous.routed.request,
                target=previous.routed.target,
                origin=previous.routed.origin,
                replayed=True,
            )
        owners = tuple(session for session in sessions if request.command in session.manifest.controls)
        if len(owners) != 1:
            raise BrokerAdmissionError(
                "control_owner_conflict" if owners else "unknown_control", "control ownership is not unique"
            )
        routed = RoutedControl(str(uuid4()), record.event.kernel_event_id, request, owners[0], session)
        record.controls[key] = _Control(routed=routed, canonical_request=canonical)
        self._control_index[routed.invocation_id] = record.controls[key]
        self._record_transition(record, "control.routed", target_bridge_id=owners[0].bridge_id)
        return routed

    def route_runtime_api(
        self, session: BridgeSession, request: RuntimeApiInvoke, sessions: tuple[BridgeSession, ...]
    ) -> RoutedRuntimeApi:
        delivery = self._require_delivery(session, request.delivery_id, request.lease_id, DeliveryState.ACTIVE)
        record = self._delivery_index[delivery.delivery_id]
        authorization = request.authorization
        if authorization.event_id != record.event.kernel_event_id:
            raise BrokerAdmissionError(
                "runtime_api_authorization_mismatch",
                "runtime API authorization does not match the routed event",
            )
        if request.source_event_id != record.event.source_event_id:
            raise BrokerAdmissionError(
                "runtime_api_source_event_mismatch",
                "runtime API source event does not match the routed event",
            )
        if authorization.runtime_id != record.event.source_bridge_id:
            raise BrokerAdmissionError(
                "runtime_api_authorization_mismatch",
                "runtime API authorization runtime does not match the routed event",
            )
        event_payload = record.event.payload
        if isinstance(event_payload, Mapping):
            event_bot_id = event_payload.get("bot_id")
            if isinstance(event_bot_id, str) and authorization.bot_id != event_bot_id:
                raise BrokerAdmissionError(
                    "runtime_api_authorization_mismatch",
                    "runtime API authorization bot does not match the routed event",
                )
            event_actor = event_payload.get("actor")
            if isinstance(event_actor, Mapping):
                event_actor_id = event_actor.get("id")
                if isinstance(event_actor_id, str) and authorization.actor_id != event_actor_id:
                    raise BrokerAdmissionError(
                        "runtime_api_authorization_mismatch",
                        "runtime API authorization actor does not match the routed event",
                    )
        canonical = json.dumps(
            request.model_dump(mode="json", exclude_none=True), sort_keys=True, separators=(",", ":")
        )
        key = (session.session_id, request.correlation_id)
        previous = record.runtime_apis.get(key)
        if previous is not None:
            if previous.canonical_request != canonical:
                raise BrokerAdmissionError(
                    "runtime_api_conflict",
                    "correlation ID was already used with different runtime API content",
                )
            return RoutedRuntimeApi(
                invocation_id=previous.routed.invocation_id,
                event_id=previous.routed.event_id,
                request=previous.routed.request,
                target=previous.routed.target,
                origin=previous.routed.origin,
                replayed=True,
            )
        owners = tuple(
            candidate
            for candidate in sessions
            if (request.bridge_id is None or candidate.bridge_id == request.bridge_id)
            and any(
                api.runtime_kind == request.runtime_kind
                and api.api_id == request.api_id
                and runtime_version_matches(request.version, api.version)
                for api in candidate.manifest.runtime_apis
            )
        )
        if len(owners) != 1:
            raise BrokerAdmissionError(
                "runtime_api_owner_conflict" if owners else "unknown_runtime_api",
                "runtime API ownership is not unique",
            )
        routed = RoutedRuntimeApi(str(uuid4()), record.event.kernel_event_id, request, owners[0], session)
        record.runtime_apis[key] = _RuntimeApi(routed=routed, canonical_request=canonical)
        self._runtime_api_index[routed.invocation_id] = record.runtime_apis[key]
        self._record_transition(record, "runtime_api.routed", target_bridge_id=owners[0].bridge_id)
        return routed

    def complete_tool(
        self,
        session: BridgeSession,
        invocation_id: str,
        *,
        success: bool,
        result: JsonValue = None,
        error_code: str | None = None,
        error_details: Mapping[str, JsonValue] | None = None,
    ) -> ToolResult:
        self.expire()
        tool = self._tool_index.get(invocation_id)
        if tool is None:
            raise BrokerAdmissionError("unknown_tool_invocation", "Tool invocation is not retained")
        if tool.routed.target.session_id != session.session_id:
            raise BrokerAdmissionError("tool_owner_mismatch", "Tool result owner does not match route")
        response = ToolResult(
            invocation_id=invocation_id,
            correlation_id=tool.routed.request.correlation_id,
            success=success,
            result=result,
            error_code=error_code,
            error_details=error_details,
        )
        if tool.result is None:
            tool.result = response
            record = self._record_for_tool(tool)
            self._record_transition(record, "tool.completed", target_bridge_id=session.bridge_id, success=success)
        elif tool.result != response:
            raise BrokerAdmissionError("tool_result_conflict", "Tool result conflicts with retained result")
        return tool.result

    def complete_control(
        self,
        session: BridgeSession,
        invocation_id: str,
        *,
        success: bool,
        result: JsonValue = None,
        error_code: str | None = None,
        error_details: Mapping[str, JsonValue] | None = None,
    ) -> BridgeControlResult:
        self.expire()
        control = self._control_index.get(invocation_id)
        if control is None:
            raise BrokerAdmissionError("unknown_control_invocation", "control invocation is not retained")
        if control.routed.target.session_id != session.session_id:
            raise BrokerAdmissionError("control_owner_mismatch", "control result owner does not match route")
        response = BridgeControlResult(
            invocation_id=invocation_id,
            correlation_id=control.routed.request.correlation_id,
            success=success,
            result=result,
            error_code=error_code,
            error_details=error_details,
        )
        if control.result is None:
            control.result = response
            record = self._record_for_control(control)
            self._record_transition(record, "control.completed", target_bridge_id=session.bridge_id, success=success)
        elif control.result != response:
            raise BrokerAdmissionError("control_result_conflict", "control result conflicts with retained result")
        return control.result

    def complete_runtime_api(
        self,
        session: BridgeSession,
        invocation_id: str,
        *,
        success: bool,
        result: JsonValue = None,
        error_code: str | None = None,
        error_details: Mapping[str, JsonValue] | None = None,
    ) -> RuntimeApiResult:
        self.expire()
        runtime_api = self._runtime_api_index.get(invocation_id)
        if runtime_api is None:
            raise BrokerAdmissionError("unknown_runtime_api_invocation", "runtime API invocation is not retained")
        if runtime_api.routed.target.session_id != session.session_id:
            raise BrokerAdmissionError("runtime_api_owner_mismatch", "runtime API result owner does not match route")
        response = RuntimeApiResult(
            invocation_id=invocation_id,
            correlation_id=runtime_api.routed.request.correlation_id,
            success=success,
            result=result,
            error_code=error_code,
            error_details=error_details,
        )
        if runtime_api.result is None:
            runtime_api.result = response
            record = self._record_for_runtime_api(runtime_api)
            self._record_transition(
                record, "runtime_api.completed", target_bridge_id=session.bridge_id, success=success
            )
        elif runtime_api.result != response:
            raise BrokerAdmissionError(
                "runtime_api_result_conflict",
                "runtime API result conflicts with retained result",
            )
        return runtime_api.result

    def tool_route(self, invocation_id: str) -> RoutedTool:
        self.expire()
        tool = self._tool_index.get(invocation_id)
        if tool is None:
            raise BrokerAdmissionError("unknown_tool_invocation", "Tool invocation is not retained")
        return tool.routed

    def tool_result(self, invocation_id: str, session: BridgeSession) -> ToolResult | None:
        tool = self._tool_index.get(invocation_id)
        if tool is None:
            raise BrokerAdmissionError("unknown_tool_invocation", "Tool invocation is not retained")
        if tool.routed.origin.session_id != session.session_id:
            raise BrokerAdmissionError("tool_origin_mismatch", "Tool result replay origin does not match route")
        return tool.result

    def control_route(self, invocation_id: str) -> RoutedControl:
        self.expire()
        control = self._control_index.get(invocation_id)
        if control is None:
            raise BrokerAdmissionError("unknown_control_invocation", "control invocation is not retained")
        return control.routed

    def control_result(self, invocation_id: str, session: BridgeSession) -> BridgeControlResult | None:
        control = self._control_index.get(invocation_id)
        if control is None:
            raise BrokerAdmissionError("unknown_control_invocation", "control invocation is not retained")
        if control.routed.origin.session_id != session.session_id:
            raise BrokerAdmissionError("control_origin_mismatch", "control replay origin does not match route")
        return control.result

    def runtime_api_route(self, invocation_id: str) -> RoutedRuntimeApi:
        self.expire()
        runtime_api = self._runtime_api_index.get(invocation_id)
        if runtime_api is None:
            raise BrokerAdmissionError("unknown_runtime_api_invocation", "runtime API invocation is not retained")
        return runtime_api.routed

    def runtime_api_result(self, invocation_id: str, session: BridgeSession) -> RuntimeApiResult | None:
        runtime_api = self._runtime_api_index.get(invocation_id)
        if runtime_api is None:
            raise BrokerAdmissionError("unknown_runtime_api_invocation", "runtime API invocation is not retained")
        if runtime_api.routed.origin.session_id != session.session_id:
            raise BrokerAdmissionError("runtime_api_origin_mismatch", "runtime API replay origin does not match route")
        return runtime_api.result

    def complete_action(
        self,
        session: BridgeSession,
        action_id: str,
        *,
        success: bool,
        payload: JsonValue = None,
    ) -> ActionResult:
        self.expire()
        action = self._action_index.get(action_id)
        if action is None:
            raise BrokerAdmissionError("unknown_action", "broker action is not retained")
        if action.routed.target.session_id != session.session_id:
            raise BrokerAdmissionError("action_owner_mismatch", "action response owner does not match route")
        _validate_json(payload, "action result")
        if action.result is None:
            action.result = ActionResult(
                action_id=action_id,
                correlation_id=action.routed.request.correlation_id,
                success=success,
                payload=payload,
            )
            record = self._record_for_action(action)
            self._record_transition(
                record,
                "action.completed",
                target_bridge_id=session.bridge_id,
                success=success,
            )
        elif action.result.success != success or self._canonical_json(action.result.payload) != self._canonical_json(
            payload
        ):
            raise BrokerAdmissionError(
                "action_result_conflict",
                "action result conflicts with the retained result",
            )
        return action.result

    @staticmethod
    def _canonical_json(value: JsonValue) -> str:
        return json.dumps(_thaw(value), sort_keys=True, separators=(",", ":"))

    def action_route(self, action_id: str) -> RoutedAction:
        """Return retained action routing only for broker-side result forwarding."""

        self.expire()
        action = self._action_index.get(action_id)
        if action is None:
            raise BrokerAdmissionError("unknown_action", "broker action is not retained")
        return action.routed

    def action_result(self, action_id: str, session: BridgeSession) -> ActionResult | None:
        """Return a retained result for replay, without dispatching the owner again."""

        self.expire()
        action = self._action_index.get(action_id)
        if action is None:
            raise BrokerAdmissionError("unknown_action", "broker action is not retained")
        if action.routed.origin.session_id != session.session_id:
            raise BrokerAdmissionError("action_origin_mismatch", "action replay origin does not match route")
        return action.result

    def disconnect_bridge(self, bridge_id: str) -> None:
        self.expire()
        for record in tuple(self._active.values()):
            for delivery in tuple(record.deliveries.values()):
                if delivery.target_bridge_id == bridge_id and delivery.state not in _TERMINAL_STATES:
                    delivery.state = DeliveryState.FAILED
                    delivery.failure_reason = "bridge_disconnected"
                    self._record_delivery_transition(delivery, "delivery.disconnected")
                    self._terminalize_delivery(delivery)

    def expire(self) -> None:
        now = self._monotonic()
        for record in tuple(self._active.values()):
            for delivery in tuple(record.deliveries.values()):
                if (
                    delivery.lease_deadline is not None
                    and now >= delivery.lease_deadline
                    and delivery.state not in _TERMINAL_STATES
                ):
                    delivery.state = DeliveryState.EXPIRED
                    delivery.failure_reason = "lease_expired"
                    self._record_delivery_transition(delivery, "delivery.expired")
                    self._terminalize_delivery(delivery)
        self._expire_terminal_records(now)

    def _expire_terminal_records(self, now: float) -> None:
        while self._terminal_order:
            event_id = self._terminal_order[0]
            record = self._terminal[event_id]
            terminal_at = record.terminal_at if record.terminal_at is not None else now
            if len(self._terminal) <= self.terminal_capacity and now - terminal_at < self.terminal_ttl_seconds:
                break
            self._terminal_order.popleft()
            self._terminal.pop(event_id, None)
            for action_id in tuple(action.routed.action_id for action in record.actions.values()):
                self._action_index.pop(action_id, None)
            for invocation_id in tuple(tool.routed.invocation_id for tool in record.tools.values()):
                self._tool_index.pop(invocation_id, None)
            for invocation_id in tuple(control.routed.invocation_id for control in record.controls.values()):
                self._control_index.pop(invocation_id, None)
            for invocation_id in tuple(api.routed.invocation_id for api in record.runtime_apis.values()):
                self._runtime_api_index.pop(invocation_id, None)

    @staticmethod
    def event_subscribers(event: BrokerEvent, sessions: tuple[BridgeSession, ...]) -> tuple[BridgeSession, ...]:
        return tuple(
            session
            for session in sessions
            if session.manifest.access is BridgeAccess.FULL
            or any(topic_pattern_matches(pattern, event.topic) for pattern in session.manifest.subscriptions)
        )

    def _offer_next(self, lane: tuple[str, str, str]) -> _Delivery | None:
        queue = self._lanes.get(lane)
        if not queue:
            return None
        delivery = self._delivery(queue[0])
        if delivery.state is not DeliveryState.PENDING:
            return None
        delivery.state = DeliveryState.OFFERED
        delivery.lease_id = secrets.token_urlsafe(24)
        delivery.lease_deadline = self._monotonic() + self.delivery_timeout_seconds
        self._record_delivery_transition(delivery, "delivery.offered")
        return delivery

    def _require_delivery(
        self,
        session: BridgeSession,
        delivery_id: str,
        lease_id: str,
        required_state: DeliveryState,
    ) -> _Delivery:
        self.expire()
        record = self._delivery_index.get(delivery_id)
        if record is None:
            raise BrokerAdmissionError("unknown_delivery", "delivery is no longer active")
        delivery = record.deliveries[delivery_id]
        if delivery.target_bridge_id != session.bridge_id:
            raise BrokerAdmissionError("delivery_owner_mismatch", "delivery belongs to a different bridge")
        if not secrets.compare_digest(delivery.lease_id, lease_id):
            raise BrokerAdmissionError("invalid_lease", "delivery lease is invalid")
        if delivery.state is not required_state:
            raise BrokerAdmissionError("invalid_delivery_state", "delivery is not in the required state")
        return delivery

    def _resolve_owner(self, kind: str, resource_key: str, sessions: tuple[BridgeSession, ...]) -> BridgeSession:
        exact_candidates: list[BridgeSession] = []
        prefix_candidates: list[tuple[int, BridgeSession]] = []
        for session in sessions:
            for declaration in session.manifest.action_resources:
                if declaration.kind != kind or not declaration.matches(resource_key):
                    continue
                if declaration.is_exact:
                    exact_candidates.append(session)
                else:
                    assert declaration.resource_prefix is not None
                    prefix_candidates.append((len(declaration.resource_prefix), session))

        exact_owner = self._select_owner(exact_candidates)
        if exact_owner is not None:
            return exact_owner

        for access in (BridgeAccess.FULL, BridgeAccess.LIMITED):
            selected = [(length, session) for length, session in prefix_candidates if session.manifest.access is access]
            if not selected:
                continue
            longest = max(length for length, _ in selected)
            matches = tuple(session for length, session in selected if length == longest)
            if len(matches) != 1:
                raise BrokerAdmissionError("ambiguous_owner", "multiple resource owners match the action")
            return matches[0]
        raise BrokerAdmissionError("unknown_action_owner", "no registered bridge owns the requested action resource")

    @staticmethod
    def _select_owner(candidates: list[BridgeSession]) -> BridgeSession | None:
        if not candidates:
            return None
        for access in (BridgeAccess.FULL, BridgeAccess.LIMITED):
            matches = tuple(session for session in candidates if session.manifest.access is access)
            if not matches:
                continue
            if len(matches) != 1:
                raise BrokerAdmissionError(
                    "ambiguous_owner", "multiple resource owners match the exact action resource"
                )
            return matches[0]
        return None

    def _terminalize_delivery(self, delivery: _Delivery) -> _Delivery | None:
        record = self._delivery_index[delivery.delivery_id]
        queue = self._lanes.get(delivery.lane)
        next_delivery = None
        if queue is not None:
            if queue and queue[0] == delivery.delivery_id:
                queue.popleft()
            else:
                queue.remove(delivery.delivery_id)
            if queue:
                next_delivery = self._offer_next(delivery.lane)
            else:
                self._lanes.pop(delivery.lane, None)
        if all(item.state in _TERMINAL_STATES for item in record.deliveries.values()):
            self._settle(record)
        return next_delivery

    def _settle(self, record: _EventRecord) -> None:
        if record.terminal_at is not None:
            return
        record.terminal_at = self._monotonic()
        self._record_transition(record, "event.settled")
        event_id = record.event.kernel_event_id
        self._active.pop(event_id, None)
        self._active_order.remove(event_id)
        for delivery_id in record.deliveries:
            self._delivery_index.pop(delivery_id, None)
        self._terminal[event_id] = record
        self._terminal_order.append(event_id)
        # Settling can exceed the retention cap before the next public operation.
        self._expire_terminal_records(record.terminal_at)

    def _delivery(self, delivery_id: str) -> _Delivery:
        record = self._delivery_index.get(delivery_id)
        if record is None:
            raise BrokerAdmissionError("unknown_delivery", "delivery is no longer active")
        return record.deliveries[delivery_id]

    def _snapshot_delivery(self, delivery: _Delivery) -> DeliverySnapshot:
        remaining = 0
        if delivery.lease_deadline is not None and delivery.state not in _TERMINAL_STATES:
            remaining = max(0, int((delivery.lease_deadline - self._monotonic()) * 1000))
        return DeliverySnapshot(
            delivery_id=delivery.delivery_id,
            target_bridge_id=delivery.target_bridge_id,
            state=delivery.state,
            attempt=1,
            lease_id=delivery.lease_id,
            lease_ttl_ms=remaining,
            failure_reason=delivery.failure_reason,
        )

    def _record_for_action(self, action: _Action) -> _EventRecord:
        record = self._active.get(action.routed.event_id) or self._terminal.get(action.routed.event_id)
        if record is None:
            raise BrokerAdmissionError("unknown_action", "broker action is not retained")
        return record

    def _record_for_tool(self, tool: _Tool) -> _EventRecord:
        record = self._active.get(tool.routed.event_id) or self._terminal.get(tool.routed.event_id)
        if record is None:
            raise BrokerAdmissionError("unknown_tool_invocation", "Tool invocation event is not retained")
        return record

    def _record_for_control(self, control: _Control) -> _EventRecord:
        record = self._active.get(control.routed.event_id) or self._terminal.get(control.routed.event_id)
        if record is None:
            raise BrokerAdmissionError("unknown_control_invocation", "control invocation event is not retained")
        return record

    def _record_for_runtime_api(self, runtime_api: _RuntimeApi) -> _EventRecord:
        record = self._active.get(runtime_api.routed.event_id) or self._terminal.get(runtime_api.routed.event_id)
        if record is None:
            raise BrokerAdmissionError(
                "unknown_runtime_api_invocation",
                "runtime API invocation event is not retained",
            )
        return record

    def _record_delivery_transition(
        self,
        delivery: _Delivery,
        kind: str,
        *,
        success: bool | None = None,
    ) -> None:
        record = self._delivery_index.get(delivery.delivery_id)
        if record is None:
            raise BrokerAdmissionError("unknown_delivery", "delivery is no longer active")
        self._record_transition(
            record,
            kind,
            target_bridge_id=delivery.target_bridge_id,
            state=delivery.state,
            success=success,
            failure_reason=delivery.failure_reason,
        )

    def _record_transition(
        self,
        record: _EventRecord,
        kind: str,
        *,
        target_bridge_id: str | None = None,
        state: DeliveryState | None = None,
        success: bool | None = None,
        failure_reason: str | None = None,
    ) -> None:
        record.transitions.append(
            LedgerTransition(
                order=len(record.transitions),
                elapsed_ms=max(0, int((self._monotonic() - record.admitted_at) * 1_000)),
                kind=kind,
                target_bridge_id=target_bridge_id,
                state=state,
                success=success,
                failure_reason=failure_reason,
            )
        )
