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
from .peer import BridgeRegistrationError, BridgeSession
from .protocol import BROKER_PROTOCOL_VERSION, BridgeAccess


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
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
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

    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
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
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
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
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    delivery_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    lease_ttl_ms: int = Field(ge=1)
    attempt: Literal[1] = 1
    event: BrokerEvent


class EventAccepted(BrokerModel):
    """Bridge acknowledgement that transitions an offered delivery to active."""

    type: Literal["event.accepted"] = "event.accepted"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    delivery_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)


class EventCompleted(BrokerModel):
    """Terminal outcome of an active broker event delivery."""

    type: Literal["event.completed"] = "event.completed"
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
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
    protocol: Literal[6] = BROKER_PROTOCOL_VERSION
    action_id: str = Field(min_length=1)
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


@dataclass(frozen=True, slots=True)
class RoutedAction:
    action_id: str
    event_id: str
    request: ActionRequest
    target: BridgeSession
    origin: BridgeSession


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
class _EventRecord:
    event: BrokerEvent
    deliveries: dict[str, _Delivery] = field(default_factory=dict)
    actions: dict[tuple[str, str], _Action] = field(default_factory=dict)
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
        record = _EventRecord(event=event)
        self._active[event.kernel_event_id] = record
        self._active_order.append(event.kernel_event_id)
        for target in self.event_subscribers(event, sessions):
            delivery_id = str(uuid4())
            lane = (session.bridge_id, ingress.ordering_key, target.bridge_id)
            delivery = _Delivery(delivery_id, event.kernel_event_id, target.bridge_id, lane)
            record.deliveries[delivery_id] = delivery
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
            delivery.failure_reason
            for delivery in record.deliveries.values()
            if delivery.failure_reason is not None
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
        return self._snapshot_delivery(delivery)

    def activate_delivery(self, session: BridgeSession, delivery_id: str, lease_id: str) -> DeliverySnapshot:
        delivery = self._require_delivery(session, delivery_id, lease_id, DeliveryState.ACCEPTED)
        delivery.state = DeliveryState.ACTIVE
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
        record = self._delivery_index[delivery.delivery_id]
        if success:
            delivery.state = DeliveryState.COMPLETED
        else:
            delivery.state = DeliveryState.FAILED
            delivery.failure_reason = failure_reason or "bridge_failed"
        next_delivery = self._terminalize_delivery(delivery)
        next_offer = None
        if next_delivery is not None:
            next_offer = (record.event, self._snapshot_delivery(next_delivery))
        return self._snapshot_delivery(delivery), next_offer

    def route_action(
        self,
        session: BridgeSession,
        request: ActionRequest,
        sessions: tuple[BridgeSession, ...],
    ) -> RoutedAction:
        delivery = self._require_delivery(session, request.delivery_id, request.lease_id, DeliveryState.ACTIVE)
        record = self._delivery_index[delivery.delivery_id]
        target = self._resolve_owner(request.kind, request.resource_key, sessions)
        key = (target.session_id, request.correlation_id)
        canonical = json.dumps(
            request.model_dump(mode="json", by_alias=True, exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
        )
        previous = record.actions.get(key)
        if previous is not None:
            if previous.canonical_request != canonical:
                raise BrokerAdmissionError("action_conflict", "correlation ID was already used with different content")
            return previous.routed
        routed = RoutedAction(str(uuid4()), record.event.kernel_event_id, request, target, session)
        record.actions[key] = _Action(routed=routed, canonical_request=canonical)
        return routed

    def complete_action(
        self,
        session: BridgeSession,
        action_id: str,
        *,
        success: bool,
        payload: JsonValue = None,
    ) -> ActionResult:
        self.expire()
        for record in (*self._active.values(), *self._terminal.values()):
            for action in record.actions.values():
                if action.routed.action_id != action_id:
                    continue
                if action.routed.target.session_id != session.session_id:
                    raise BrokerAdmissionError("action_owner_mismatch", "action response owner does not match route")
                _validate_json(payload, "action result")
                if action.result is None:
                    action.result = ActionResult(action_id=action_id, success=success, payload=payload)
                elif (
                    action.result.success != success
                    or self._canonical_json(action.result.payload) != self._canonical_json(payload)
                ):
                    raise BrokerAdmissionError(
                        "action_result_conflict",
                        "action result conflicts with the retained result",
                    )
                return action.result
        raise BrokerAdmissionError("unknown_action", "broker action is not retained")

    @staticmethod
    def _canonical_json(value: JsonValue) -> str:
        return json.dumps(_thaw(value), sort_keys=True, separators=(",", ":"))

    def action_route(self, action_id: str) -> RoutedAction:
        """Return retained action routing only for broker-side result forwarding."""

        self.expire()
        for record in (*self._active.values(), *self._terminal.values()):
            for action in record.actions.values():
                if action.routed.action_id == action_id:
                    return action.routed
        raise BrokerAdmissionError("unknown_action", "broker action is not retained")

    def disconnect_bridge(self, bridge_id: str) -> None:
        self.expire()
        for record in tuple(self._active.values()):
            for delivery in tuple(record.deliveries.values()):
                if delivery.target_bridge_id == bridge_id and delivery.state not in _TERMINAL_STATES:
                    delivery.state = DeliveryState.FAILED
                    delivery.failure_reason = "bridge_disconnected"
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
                    self._terminalize_delivery(delivery)
        while self._terminal_order:
            event_id = self._terminal_order[0]
            record = self._terminal[event_id]
            terminal_at = record.terminal_at if record.terminal_at is not None else now
            if len(self._terminal) <= self.terminal_capacity and now - terminal_at < self.terminal_ttl_seconds:
                break
            self._terminal_order.popleft()
            self._terminal.pop(event_id, None)

    @staticmethod
    def event_subscribers(event: BrokerEvent, sessions: tuple[BridgeSession, ...]) -> tuple[BridgeSession, ...]:
        return tuple(
            session
            for session in sessions
            if session.manifest.access is BridgeAccess.FULL or event.topic in session.manifest.subscriptions
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
        candidates: list[tuple[int, BridgeSession]] = []
        for session in sessions:
            for declaration in session.manifest.action_resources:
                if declaration.kind == kind and resource_key.startswith(declaration.resource_prefix):
                    candidates.append((len(declaration.resource_prefix), session))
        for access in (BridgeAccess.FULL, BridgeAccess.LIMITED):
            selected = [(length, session) for length, session in candidates if session.manifest.access is access]
            if not selected:
                continue
            longest = max(length for length, _ in selected)
            matches = tuple(session for length, session in selected if length == longest)
            if len(matches) != 1:
                raise BrokerAdmissionError("ambiguous_owner", "multiple resource owners match the action")
            return matches[0]
        raise BrokerAdmissionError("unknown_action_owner", "no registered bridge owns the requested action resource")

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
        event_id = record.event.kernel_event_id
        self._active.pop(event_id, None)
        self._active_order.remove(event_id)
        for delivery_id in record.deliveries:
            self._delivery_index.pop(delivery_id, None)
        self._terminal[event_id] = record
        self._terminal_order.append(event_id)
        self.expire()

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
