"""Kernel-owned, bounded in-memory event delivery ledger.

The ledger is deliberately transport- and framework-neutral.  A runtime host
offers ``DeliverySnapshot`` values, reports lifecycle transitions, and asks
the ledger to validate side effects.  It never hands mutable event state to a
child runtime.
"""

from __future__ import annotations

import json
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal, cast
from uuid import uuid4

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | tuple[JsonValue, ...] | Mapping[str, JsonValue]
type DeliveryPolicy = Literal["required", "best_effort"]
type DeliveryCompletion = Literal["sync", "async"]
type OrderingLane = tuple[str, str, str, str]


class EventLedgerError(RuntimeError):
    """Base error for event ledger contract violations."""


class EventLedgerCapacityError(EventLedgerError):
    """Raised when admitting another active event would exceed capacity."""


class UnknownLedgerRecordError(EventLedgerError):
    """Raised when an event or delivery is no longer retained."""


class DeliveryTransitionError(EventLedgerError):
    """Raised for a lifecycle transition that does not match current state."""


class DeliveryLeaseError(EventLedgerError):
    """Raised when a child uses a missing, stale, or invalid delivery lease."""


class ActionDeduplicationConflictError(EventLedgerError):
    """Raised when one action correlation id is reused with different content."""


class DeliveryState(StrEnum):
    """A delivery's kernel lifecycle.

    ``PENDING`` is internal queueing state: it has not consumed a target's
    handler timeout.  All other states are observable by a runtime host.
    """

    PENDING = "pending"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class DeliveryTerminalReason(StrEnum):
    COMPLETED = "completed"
    RUNTIME_REJECTED = "runtime_rejected"
    OVERLOADED = "overloaded"
    DISCONNECTED = "disconnected"
    STALE_LEASE = "stale_lease"
    SEND_FAILED = "send_failed"
    DEADLINE_EXPIRED = "deadline_expired"
    KERNEL_SHUTDOWN = "kernel_shutdown"
    RUNTIME_FAILED = "runtime_failed"


class EventState(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionClaimState(StrEnum):
    NEW = "new"
    PENDING = "pending"
    RECORDED = "recorded"


@dataclass(frozen=True, slots=True)
class EventProvenance:
    """Source identity used for event ownership and delivery ordering."""

    source_runtime_id: str
    source_event_id: str
    bot_id: str
    conversation_id: str

    def __post_init__(self) -> None:
        _require_identifier("source_runtime_id", self.source_runtime_id)
        _require_identifier("source_event_id", self.source_event_id)
        _require_identifier("bot_id", self.bot_id)
        _require_identifier("conversation_id", self.conversation_id)


@dataclass(frozen=True, slots=True)
class RouteSnapshot:
    """A matched route frozen at event admission time."""

    target_runtime_id: str
    policy: DeliveryPolicy = "required"
    completion: DeliveryCompletion = "async"
    messages_only: bool = False

    def __post_init__(self) -> None:
        _require_identifier("target_runtime_id", self.target_runtime_id)
        if self.policy not in {"required", "best_effort"}:
            raise ValueError("route policy must be required or best_effort")
        if self.completion not in {"sync", "async"}:
            raise ValueError("route completion must be sync or async")
        if not isinstance(self.messages_only, bool):
            raise ValueError("route messages_only must be a boolean")


@dataclass(frozen=True, slots=True)
class DeliverySnapshot:
    """Immutable transport work item and retained delivery diagnosis."""

    event_id: str
    delivery_id: str
    provenance: EventProvenance
    route: RouteSnapshot
    state: DeliveryState
    attempt: int
    lease_id: str | None
    deadline: float | None
    admitted_at: float
    offered_at: float | None
    accepted_at: float | None
    active_at: float | None
    terminal_at: float | None
    terminal_reason: DeliveryTerminalReason | None

    @property
    def ordering_lane(self) -> OrderingLane:
        return (
            self.provenance.source_runtime_id,
            self.provenance.bot_id,
            self.provenance.conversation_id,
            self.route.target_runtime_id,
        )

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL_DELIVERY_STATES


@dataclass(frozen=True, slots=True)
class ActionRecordSnapshot:
    """One event-and-target scoped action idempotency record."""

    target_runtime_id: str
    correlation_id: str
    payload: JsonValue
    claimed_at: float
    result: JsonValue | None
    completed_at: float | None


@dataclass(frozen=True, slots=True)
class EventSnapshot:
    """An immutable admitted event, its route snapshot, and deliveries."""

    event_id: str
    provenance: EventProvenance
    payload: Mapping[str, JsonValue]
    routes: tuple[RouteSnapshot, ...]
    deliveries: tuple[DeliverySnapshot, ...]
    actions: tuple[ActionRecordSnapshot, ...]
    state: EventState
    admitted_at: float
    terminal_at: float | None

    @property
    def terminal(self) -> bool:
        return self.state is not EventState.ACTIVE

    @property
    def required_deliveries_terminal(self) -> bool:
        return all(delivery.terminal for delivery in self.deliveries if delivery.route.policy == "required")

    @property
    def required_deliveries_succeeded(self) -> bool | None:
        if not self.required_deliveries_terminal:
            return None
        return all(
            delivery.state is DeliveryState.COMPLETED
            for delivery in self.deliveries
            if delivery.route.policy == "required"
        )


@dataclass(frozen=True, slots=True)
class ActionClaim:
    """Result of atomically registering or replaying an action request."""

    state: ActionClaimState
    record: ActionRecordSnapshot


@dataclass(slots=True)
class _ActionRecord:
    target_runtime_id: str
    correlation_id: str
    payload: JsonValue
    canonical_payload: str
    claimed_at: float
    result: JsonValue | None = None
    completed_at: float | None = None


@dataclass(slots=True)
class _DeliveryRecord:
    event_id: str
    delivery_id: str
    provenance: EventProvenance
    route: RouteSnapshot
    admitted_at: float
    state: DeliveryState = DeliveryState.PENDING
    attempt: int = 1
    lease_id: str | None = None
    deadline: float | None = None
    offered_at: float | None = None
    accepted_at: float | None = None
    active_at: float | None = None
    terminal_at: float | None = None
    terminal_reason: DeliveryTerminalReason | None = None

    @property
    def lane(self) -> OrderingLane:
        return (
            self.provenance.source_runtime_id,
            self.provenance.bot_id,
            self.provenance.conversation_id,
            self.route.target_runtime_id,
        )


@dataclass(slots=True)
class _EventRecord:
    event_id: str
    provenance: EventProvenance
    payload: Mapping[str, JsonValue]
    routes: tuple[RouteSnapshot, ...]
    deliveries: dict[str, _DeliveryRecord]
    admitted_at: float
    actions: dict[tuple[str, str], _ActionRecord] = field(default_factory=dict)
    terminal_at: float | None = None
    state: EventState = EventState.ACTIVE


_TERMINAL_DELIVERY_STATES = frozenset(
    {DeliveryState.COMPLETED, DeliveryState.FAILED, DeliveryState.EXPIRED}
)


class EventLedger:
    """Own bounded active and terminal event history without transport imports.

    All public methods are synchronous and make no awaits.  They are therefore
    atomic with respect to a normal asyncio event-loop caller; callers should
    serialize access if they invoke the ledger from multiple OS threads.
    """

    def __init__(
        self,
        *,
        active_capacity: int = 1_024,
        terminal_capacity: int = 16_384,
        terminal_ttl_seconds: float = 3_600,
        clock: Callable[[], float] = time.monotonic,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        if active_capacity < 1:
            raise ValueError("active_capacity must be at least one")
        if terminal_capacity < 1:
            raise ValueError("terminal_capacity must be at least one")
        if terminal_ttl_seconds <= 0:
            raise ValueError("terminal_ttl_seconds must be positive")
        self._active_capacity = active_capacity
        self._terminal_capacity = terminal_capacity
        self._terminal_ttl_seconds = terminal_ttl_seconds
        self._clock = clock
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._active: dict[str, _EventRecord] = {}
        self._terminal: OrderedDict[str, _EventRecord] = OrderedDict()
        self._lanes: dict[OrderingLane, deque[str]] = {}

    @property
    def active_capacity(self) -> int:
        return self._active_capacity

    @property
    def terminal_capacity(self) -> int:
        return self._terminal_capacity

    @property
    def terminal_ttl_seconds(self) -> float:
        return self._terminal_ttl_seconds

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def terminal_count(self) -> int:
        self.purge()
        return len(self._terminal)

    def admit(
        self,
        *,
        provenance: EventProvenance,
        payload: Mapping[str, Any],
        routes: Sequence[RouteSnapshot],
    ) -> EventSnapshot:
        """Freeze one matching route set and queue one delivery per target."""

        now = self._clock()
        self._purge_terminal(now)
        if len(self._active) >= self._active_capacity:
            raise EventLedgerCapacityError("event ledger active capacity is exhausted")
        frozen_payload = _freeze_mapping(payload)
        frozen_routes = tuple(routes)
        targets = [route.target_runtime_id for route in frozen_routes]
        if len(set(targets)) != len(targets):
            raise ValueError("an admitted event cannot have multiple deliveries for one target runtime")
        event_id = self._new_unique_id()
        deliveries: dict[str, _DeliveryRecord] = {}
        for route in frozen_routes:
            delivery_id = self._new_unique_id()
            delivery = _DeliveryRecord(
                event_id=event_id,
                delivery_id=delivery_id,
                provenance=provenance,
                route=route,
                admitted_at=now,
            )
            deliveries[delivery_id] = delivery
        record = _EventRecord(
            event_id=event_id,
            provenance=provenance,
            payload=frozen_payload,
            routes=frozen_routes,
            deliveries=deliveries,
            admitted_at=now,
        )
        self._active[event_id] = record
        for delivery in deliveries.values():
            self._lanes.setdefault(delivery.lane, deque()).append(delivery.delivery_id)
        if not deliveries:
            self._terminalize_event(record, now)
        return self._event_snapshot(record)

    def ready_offers(self, *, delivery_timeout_seconds: float) -> tuple[DeliverySnapshot, ...]:
        """Offer the next queued delivery from every available ordering lane.

        Offering assigns the lease and begins the per-target deadline.  The
        returned snapshots contain all information a transport host needs to
        construct a child delivery message.
        """

        if delivery_timeout_seconds <= 0:
            raise ValueError("delivery_timeout_seconds must be positive")
        now = self._clock()
        self._expire(now)
        offers: list[DeliverySnapshot] = []
        for lane in tuple(self._lanes):
            delivery = self._front_delivery(lane)
            if delivery is None or delivery.state is not DeliveryState.PENDING:
                continue
            delivery.state = DeliveryState.OFFERED
            delivery.lease_id = self._new_unique_id()
            delivery.offered_at = now
            delivery.deadline = now + delivery_timeout_seconds
            offers.append(self._delivery_snapshot(delivery))
        return tuple(offers)

    def accept_delivery(self, delivery_id: str, lease_id: str) -> DeliverySnapshot:
        delivery = self._require_live_delivery(delivery_id, lease_id)
        if delivery.state is not DeliveryState.OFFERED:
            raise DeliveryTransitionError(f"delivery {delivery_id!r} cannot be accepted from {delivery.state.value}")
        delivery.state = DeliveryState.ACCEPTED
        delivery.accepted_at = self._clock()
        return self._delivery_snapshot(delivery)

    def activate_delivery(self, delivery_id: str, lease_id: str) -> DeliverySnapshot:
        delivery = self._require_live_delivery(delivery_id, lease_id)
        if delivery.state is not DeliveryState.ACCEPTED:
            raise DeliveryTransitionError(f"delivery {delivery_id!r} cannot be activated from {delivery.state.value}")
        delivery.state = DeliveryState.ACTIVE
        delivery.active_at = self._clock()
        return self._delivery_snapshot(delivery)

    def complete_delivery(self, delivery_id: str, lease_id: str) -> DeliverySnapshot:
        delivery = self._require_live_delivery(delivery_id, lease_id)
        if delivery.state not in {DeliveryState.ACCEPTED, DeliveryState.ACTIVE}:
            raise DeliveryTransitionError(f"delivery {delivery_id!r} cannot complete from {delivery.state.value}")
        self._terminalize_delivery(delivery, DeliveryState.COMPLETED, DeliveryTerminalReason.COMPLETED, self._clock())
        return self._delivery_snapshot(delivery)

    def fail_delivery(
        self,
        delivery_id: str,
        reason: DeliveryTerminalReason,
        *,
        lease_id: str | None = None,
    ) -> DeliverySnapshot:
        """Record a transport failure; a lease is required for child-originated failures."""

        delivery = self._delivery(delivery_id)
        if lease_id is not None:
            self._validate_lease(delivery, lease_id)
        if delivery.state in _TERMINAL_DELIVERY_STATES:
            return self._delivery_snapshot(delivery)
        if reason in {DeliveryTerminalReason.COMPLETED, DeliveryTerminalReason.DEADLINE_EXPIRED}:
            raise ValueError("use complete_delivery or expire for this terminal reason")
        self._terminalize_delivery(delivery, DeliveryState.FAILED, reason, self._clock())
        return self._delivery_snapshot(delivery)

    def expire(self) -> tuple[DeliverySnapshot, ...]:
        """Expire outstanding offered, accepted, or active deliveries."""

        return self._expire(self._clock())

    def shutdown(self) -> tuple[DeliverySnapshot, ...]:
        """Terminalize every active delivery before a kernel shutdown."""

        now = self._clock()
        terminated: list[DeliverySnapshot] = []
        for record in tuple(self._active.values()):
            for delivery in tuple(record.deliveries.values()):
                if delivery.state not in _TERMINAL_DELIVERY_STATES:
                    self._terminalize_delivery(
                        delivery,
                        DeliveryState.FAILED,
                        DeliveryTerminalReason.KERNEL_SHUTDOWN,
                        now,
                    )
                    terminated.append(self._delivery_snapshot(delivery))
        return tuple(terminated)

    def claim_action(
        self,
        *,
        delivery_id: str,
        lease_id: str,
        correlation_id: str,
        payload: Any,
    ) -> ActionClaim:
        """Validate an active lease and atomically reserve/replay an action.

        Replayed records are returned before the caller invokes an action owner,
        so only a ``NEW`` claim may execute a side effect.
        """

        _require_identifier("correlation_id", correlation_id)
        delivery = self._require_live_delivery(delivery_id, lease_id)
        if delivery.state is not DeliveryState.ACTIVE:
            raise DeliveryTransitionError("actions require an active delivery")
        record = self._active[delivery.event_id]
        frozen_payload = _freeze_json(payload)
        canonical_payload = _canonical_json(frozen_payload)
        key = (delivery.route.target_runtime_id, correlation_id)
        existing = record.actions.get(key)
        if existing is None:
            action = _ActionRecord(
                target_runtime_id=delivery.route.target_runtime_id,
                correlation_id=correlation_id,
                payload=frozen_payload,
                canonical_payload=canonical_payload,
                claimed_at=self._clock(),
            )
            record.actions[key] = action
            return ActionClaim(ActionClaimState.NEW, self._action_snapshot(action))
        if existing.canonical_payload != canonical_payload:
            raise ActionDeduplicationConflictError(
                "action correlation id was reused with a different canonical JSON payload"
            )
        state = ActionClaimState.RECORDED if existing.completed_at is not None else ActionClaimState.PENDING
        return ActionClaim(state, self._action_snapshot(existing))

    def record_action_result(
        self,
        *,
        delivery_id: str,
        lease_id: str,
        correlation_id: str,
        result: Any,
    ) -> ActionRecordSnapshot:
        """Persist the result that identical future action requests must reuse."""

        _require_identifier("correlation_id", correlation_id)
        delivery = self._require_live_delivery(delivery_id, lease_id)
        record = self._active[delivery.event_id]
        key = (delivery.route.target_runtime_id, correlation_id)
        action = record.actions.get(key)
        if action is None:
            raise UnknownLedgerRecordError("action result has no corresponding action claim")
        frozen_result = _freeze_json(result)
        if action.completed_at is not None:
            if _canonical_json(action.result) != _canonical_json(frozen_result):
                raise ActionDeduplicationConflictError("action result was already recorded with different content")
            return self._action_snapshot(action)
        action.result = frozen_result
        action.completed_at = self._clock()
        return self._action_snapshot(action)

    def snapshot(self, event_id: str) -> EventSnapshot:
        """Return a retained immutable event snapshot or raise when evicted."""

        self._purge_terminal(self._clock())
        record = self._active.get(event_id) or self._terminal.get(event_id)
        if record is None:
            raise UnknownLedgerRecordError(f"event {event_id!r} is not retained")
        return self._event_snapshot(record)

    def active_snapshots(self) -> tuple[EventSnapshot, ...]:
        self._expire(self._clock())
        return tuple(self._event_snapshot(record) for record in self._active.values())

    def terminal_snapshots(self) -> tuple[EventSnapshot, ...]:
        self._purge_terminal(self._clock())
        return tuple(self._event_snapshot(record) for record in self._terminal.values())

    def purge(self) -> tuple[str, ...]:
        """Evict terminal events past TTL or terminal capacity and return their ids."""

        return self._purge_terminal(self._clock())

    def _expire(self, now: float) -> tuple[DeliverySnapshot, ...]:
        expired: list[DeliverySnapshot] = []
        for record in tuple(self._active.values()):
            for delivery in tuple(record.deliveries.values()):
                if (
                    delivery.state not in _TERMINAL_DELIVERY_STATES
                    and delivery.deadline is not None
                    and delivery.deadline <= now
                ):
                    self._terminalize_delivery(
                        delivery,
                        DeliveryState.EXPIRED,
                        DeliveryTerminalReason.DEADLINE_EXPIRED,
                        now,
                    )
                    expired.append(self._delivery_snapshot(delivery))
        self._purge_terminal(now)
        return tuple(expired)

    def _delivery(self, delivery_id: str) -> _DeliveryRecord:
        _require_identifier("delivery_id", delivery_id)
        for record in self._active.values():
            delivery = record.deliveries.get(delivery_id)
            if delivery is not None:
                return delivery
        raise UnknownLedgerRecordError(f"delivery {delivery_id!r} is not active")

    def _require_live_delivery(self, delivery_id: str, lease_id: str) -> _DeliveryRecord:
        self._expire(self._clock())
        delivery = self._delivery(delivery_id)
        self._validate_lease(delivery, lease_id)
        if delivery.state in _TERMINAL_DELIVERY_STATES:
            raise DeliveryTransitionError(f"delivery {delivery_id!r} is terminal")
        return delivery

    @staticmethod
    def _validate_lease(delivery: _DeliveryRecord, lease_id: str) -> None:
        _require_identifier("lease_id", lease_id)
        if delivery.lease_id != lease_id:
            raise DeliveryLeaseError(f"delivery {delivery.delivery_id!r} has a stale or invalid lease")

    def _front_delivery(self, lane: OrderingLane) -> _DeliveryRecord | None:
        pending = self._lanes.get(lane)
        if pending is None:
            return None
        while pending:
            delivery_id = pending[0]
            try:
                delivery = self._delivery(delivery_id)
            except UnknownLedgerRecordError:
                pending.popleft()
                continue
            if delivery.state in _TERMINAL_DELIVERY_STATES:
                pending.popleft()
                continue
            return delivery
        self._lanes.pop(lane, None)
        return None

    def _terminalize_delivery(
        self,
        delivery: _DeliveryRecord,
        state: DeliveryState,
        reason: DeliveryTerminalReason,
        now: float,
    ) -> None:
        if delivery.state in _TERMINAL_DELIVERY_STATES:
            return
        delivery.state = state
        delivery.terminal_reason = reason
        delivery.terminal_at = now
        lane = self._lanes.get(delivery.lane)
        if lane is not None and lane and lane[0] == delivery.delivery_id:
            lane.popleft()
            if not lane:
                self._lanes.pop(delivery.lane, None)
        record = self._active.get(delivery.event_id)
        if record is not None and all(item.state in _TERMINAL_DELIVERY_STATES for item in record.deliveries.values()):
            self._terminalize_event(record, now)

    def _terminalize_event(self, record: _EventRecord, now: float) -> None:
        if record.event_id not in self._active:
            return
        required_failed = any(
            delivery.route.policy == "required" and delivery.state is not DeliveryState.COMPLETED
            for delivery in record.deliveries.values()
        )
        record.state = EventState.FAILED if required_failed else EventState.COMPLETED
        record.terminal_at = now
        self._active.pop(record.event_id)
        self._terminal[record.event_id] = record
        self._purge_terminal(now)

    def _purge_terminal(self, now: float) -> tuple[str, ...]:
        evicted: list[str] = []
        cutoff = now - self._terminal_ttl_seconds
        while self._terminal:
            event_id, record = next(iter(self._terminal.items()))
            if len(self._terminal) <= self._terminal_capacity and record.terminal_at is not None and record.terminal_at > cutoff:
                break
            self._terminal.pop(event_id)
            evicted.append(event_id)
        return tuple(evicted)

    def _new_unique_id(self) -> str:
        for _ in range(100):
            identifier = self._id_factory()
            _require_identifier("generated ledger id", identifier)
            if not self._identifier_in_use(identifier):
                return identifier
        raise RuntimeError("ledger id factory produced too many collisions")

    def _identifier_in_use(self, identifier: str) -> bool:
        if identifier in self._active or identifier in self._terminal:
            return True
        for record in (*self._active.values(), *self._terminal.values()):
            if identifier in record.deliveries:
                return True
            if any(delivery.lease_id == identifier for delivery in record.deliveries.values()):
                return True
        return False

    @staticmethod
    def _delivery_snapshot(delivery: _DeliveryRecord) -> DeliverySnapshot:
        return DeliverySnapshot(
            event_id=delivery.event_id,
            delivery_id=delivery.delivery_id,
            provenance=delivery.provenance,
            route=delivery.route,
            state=delivery.state,
            attempt=delivery.attempt,
            lease_id=delivery.lease_id,
            deadline=delivery.deadline,
            admitted_at=delivery.admitted_at,
            offered_at=delivery.offered_at,
            accepted_at=delivery.accepted_at,
            active_at=delivery.active_at,
            terminal_at=delivery.terminal_at,
            terminal_reason=delivery.terminal_reason,
        )

    @staticmethod
    def _action_snapshot(action: _ActionRecord) -> ActionRecordSnapshot:
        return ActionRecordSnapshot(
            target_runtime_id=action.target_runtime_id,
            correlation_id=action.correlation_id,
            payload=action.payload,
            claimed_at=action.claimed_at,
            result=action.result,
            completed_at=action.completed_at,
        )

    def _event_snapshot(self, record: _EventRecord) -> EventSnapshot:
        return EventSnapshot(
            event_id=record.event_id,
            provenance=record.provenance,
            payload=record.payload,
            routes=record.routes,
            deliveries=tuple(self._delivery_snapshot(item) for item in record.deliveries.values()),
            actions=tuple(self._action_snapshot(item) for item in record.actions.values()),
            state=record.state,
            admitted_at=record.admitted_at,
            terminal_at=record.terminal_at,
        )


def _require_identifier(name: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a non-empty trimmed string")


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, JsonValue]:
    frozen = _freeze_json(value)
    if not isinstance(frozen, Mapping):
        raise TypeError("expected a JSON object")
    return frozen


def _freeze_json(value: Any) -> JsonValue:
    """Validate and copy arbitrary JSON-compatible input into immutable shapes."""

    try:
        encoded = json.dumps(
            _mutable_json(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise TypeError("ledger values must be JSON-compatible and finite") from exc
    return _freeze_decoded_json(decoded)


def _freeze_decoded_json(value: Any) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int, float)):
        return cast(JsonScalar, value)
    if isinstance(value, list):
        return tuple(_freeze_decoded_json(item) for item in value)
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze_decoded_json(item) for key, item in value.items()})
    raise AssertionError("JSON decoding returned an unsupported value")


def _mutable_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        mutable: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("ledger JSON objects require string keys")
            mutable[key] = _mutable_json(item)
        return mutable
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_mutable_json(item) for item in value]
    return value


def _canonical_json(value: JsonValue | None) -> str:
    return json.dumps(_thaw_json(value), ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _thaw_json(value: JsonValue | None) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value
