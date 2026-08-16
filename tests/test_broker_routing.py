from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from liteyukibot.broker import (
    ActionRequest,
    ActionResourceDeclaration,
    BridgeAccess,
    BridgeManifest,
    BridgeSession,
    BrokerAdmissionError,
    BrokerLedger,
    DeliveryState,
    EventCompleted,
    EventIngress,
)


@dataclass
class Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


def _session(
    bridge_id: str,
    *,
    access: BridgeAccess = BridgeAccess.LIMITED,
    subscriptions: tuple[str, ...] = ("message.created",),
    resources: tuple[ActionResourceDeclaration, ...] = (),
) -> BridgeSession:
    return BridgeSession(
        bridge_id=bridge_id,
        session_id=f"session-{bridge_id}",
        manifest=BridgeManifest(
            bridge_id=bridge_id,
            access=access,
            subscriptions=subscriptions,
            action_resources=resources,
        ),
        peer_identity=f"{bridge_id}-peer".encode(),
    )


def _ingress(*, source_event_id: str = "source-1", ordering_key: str = "chat:1") -> EventIngress:
    return EventIngress(
        source_event_id=source_event_id,
        topic="message.created",
        ordering_key=ordering_key,
        payload={"text": "hello"},
    )


def _active_delivery(ledger: BrokerLedger, source: BridgeSession, target: BridgeSession) -> tuple[str, str, str]:
    event = ledger.admit_event(source, _ingress(), (source, target))
    offered = ledger.offered_deliveries(event.kernel_event_id)
    target_delivery = next(item for item in offered if item.target_bridge_id == target.bridge_id)
    ledger.accept_delivery(target, target_delivery.delivery_id, target_delivery.lease_id)
    ledger.activate_delivery(target, target_delivery.delivery_id, target_delivery.lease_id)
    return event.kernel_event_id, target_delivery.delivery_id, target_delivery.lease_id


def test_broker_generates_identity_and_uses_authenticated_session_provenance() -> None:
    ledger = BrokerLedger()
    source = _session("source", subscriptions=())

    first = ledger.admit_event(source, _ingress(source_event_id="platform-7"), (source,))
    second = ledger.admit_event(source, _ingress(source_event_id="platform-7", ordering_key="chat:2"), (source,))

    assert first.kernel_event_id != second.kernel_event_id
    assert first.source_bridge_id == "source"
    assert first.source_event_id == "platform-7"
    assert "event_id" not in EventIngress.model_fields


def test_active_capacity_is_independent_from_terminal_retention() -> None:
    ledger = BrokerLedger(active_capacity=1, terminal_capacity=2)
    source = _session("source", subscriptions=())
    target = _session("target")
    first = ledger.admit_event(source, _ingress(), (source, target))
    with pytest.raises(BrokerAdmissionError, match="active event capacity"):
        ledger.admit_event(source, _ingress(ordering_key="chat:2"), (source, target))
    offer = next(item for item in ledger.offered_deliveries(first.kernel_event_id) if item.target_bridge_id == "target")
    ledger.accept_delivery(target, offer.delivery_id, offer.lease_id)
    ledger.activate_delivery(target, offer.delivery_id, offer.lease_id)
    ledger.complete_delivery(target, offer.delivery_id, offer.lease_id, success=True)
    assert ledger.active_count == 0
    assert ledger.terminal_count == 1


def test_fifo_lane_offers_only_one_delivery_until_predecessor_is_terminal() -> None:
    ledger = BrokerLedger()
    source = _session("source", subscriptions=())
    target = _session("target")
    first = ledger.admit_event(source, _ingress(source_event_id="one"), (source, target))
    second = ledger.admit_event(source, _ingress(source_event_id="two"), (source, target))

    first_offer = next(
        item for item in ledger.offered_deliveries(first.kernel_event_id) if item.target_bridge_id == "target"
    )
    assert ledger.offered_deliveries(second.kernel_event_id) == ()
    ledger.accept_delivery(target, first_offer.delivery_id, first_offer.lease_id)
    ledger.activate_delivery(target, first_offer.delivery_id, first_offer.lease_id)
    _completed, next_offer = ledger.complete_delivery_with_next_offer(
        target,
        first_offer.delivery_id,
        first_offer.lease_id,
        success=True,
    )
    assert next_offer is not None
    next_event, second_offer = next_offer
    assert next_event.kernel_event_id == second.kernel_event_id
    assert second_offer.target_bridge_id == "target"
    assert second_offer.state is DeliveryState.OFFERED


def test_settlement_immediately_enforces_terminal_capacity() -> None:
    ledger = BrokerLedger(terminal_capacity=1)
    source = _session("source", subscriptions=())
    target = _session("target")

    _, first_delivery_id, first_lease_id = _active_delivery(ledger, source, target)
    ledger.complete_delivery(target, first_delivery_id, first_lease_id, success=True)
    _, second_delivery_id, second_lease_id = _active_delivery(ledger, source, target)
    ledger.complete_delivery(target, second_delivery_id, second_lease_id, success=True)

    assert ledger.terminal_count == 1


def test_terminal_retention_evicts_delivery_and_lane_indices() -> None:
    clock = Clock()
    ledger = BrokerLedger(terminal_capacity=1, terminal_ttl_seconds=5, monotonic=clock)
    source = _session("source", subscriptions=())
    target = _session("target")
    _, delivery_id, lease_id = _active_delivery(ledger, source, target)
    ledger.complete_delivery(target, delivery_id, lease_id, success=True)
    assert ledger.index_counts() == (0, 0)

    _, second_delivery_id, second_lease_id = _active_delivery(ledger, source, target)
    ledger.complete_delivery(target, second_delivery_id, second_lease_id, success=True)
    assert ledger.terminal_count == 1
    clock.now = 6
    assert ledger.terminal_count == 0


def test_delivery_state_machine_timeout_disconnect_and_settled_degraded_diagnostics() -> None:
    clock = Clock()
    ledger = BrokerLedger(delivery_timeout_seconds=5, monotonic=clock)
    source = _session("source", subscriptions=())
    target = _session("target")
    event = ledger.admit_event(source, _ingress(), (source, target))
    offered = next(
        item for item in ledger.offered_deliveries(event.kernel_event_id) if item.target_bridge_id == "target"
    )
    clock.now = 5
    ledger.expire()
    settled = ledger.event_snapshot(event.kernel_event_id)
    assert settled.status == "settled"
    assert settled.failure_reasons == ("lease_expired",)
    with pytest.raises(BrokerAdmissionError, match="no longer active"):
        ledger.accept_delivery(target, offered.delivery_id, offered.lease_id)

    event = ledger.admit_event(source, _ingress(ordering_key="chat:2"), (source, target))
    offered = next(
        item for item in ledger.offered_deliveries(event.kernel_event_id) if item.target_bridge_id == "target"
    )
    ledger.disconnect_bridge("target")
    assert ledger.event_snapshot(event.kernel_event_id).failure_reasons == ("bridge_disconnected",)
    assert offered.state is DeliveryState.OFFERED


def test_action_requires_active_lease_deduplicates_and_retains_result_until_event_eviction() -> None:
    clock = Clock()
    ledger = BrokerLedger(terminal_ttl_seconds=5, monotonic=clock)
    source = _session("source", subscriptions=())
    caller = _session("caller")
    owner = _session(
        "owner",
        resources=(ActionResourceDeclaration(kind="message.send", resource_prefix="bot:"),),
    )
    event_id, delivery_id, lease_id = _active_delivery(ledger, source, caller)
    request = ActionRequest(
        delivery_id=delivery_id,
        lease_id=lease_id,
        correlation_id="call-1",
        kind="message.send",
        resource_key="bot:42",
        payload={"text": "hello"},
    )
    routed = ledger.route_action(caller, request, (source, caller, owner))
    replay = ledger.route_action(caller, request, (source, caller, owner))
    assert replay.action_id == routed.action_id
    assert replay.replayed
    conflict = request.model_copy(update={"payload": {"text": "changed"}})
    with pytest.raises(BrokerAdmissionError, match="different content"):
        ledger.route_action(caller, conflict, (source, caller, owner))
    result = ledger.complete_action(owner, routed.action_id, success=True, payload={"message_id": "7"})
    assert result.success

    ledger.complete_delivery(caller, delivery_id, lease_id, success=True)
    assert ledger.complete_action(owner, routed.action_id, success=True, payload={"message_id": "7"}) == result
    clock.now = 6
    ledger.expire()
    with pytest.raises(BrokerAdmissionError, match="not retained"):
        ledger.complete_action(owner, routed.action_id, success=True)
    assert event_id


@pytest.mark.parametrize(
    ("success", "payload"),
    [
        (False, {"message_id": "7"}),
        (True, {"message_id": "8"}),
    ],
)
def test_action_result_replays_must_match_retained_result(success: bool, payload: dict[str, str]) -> None:
    ledger = BrokerLedger()
    source = _session("source", subscriptions=())
    caller = _session("caller")
    owner = _session(
        "owner",
        resources=(ActionResourceDeclaration(kind="message.send", resource_prefix="bot:"),),
    )
    _, delivery_id, lease_id = _active_delivery(ledger, source, caller)
    routed = ledger.route_action(
        caller,
        ActionRequest(
            delivery_id=delivery_id,
            lease_id=lease_id,
            correlation_id="call-1",
            kind="message.send",
            resource_key="bot:42",
        ),
        (source, caller, owner),
    )

    retained = ledger.complete_action(owner, routed.action_id, success=True, payload={"message_id": "7", "ok": True})
    assert (
        ledger.complete_action(owner, routed.action_id, success=True, payload={"ok": True, "message_id": "7"})
        == retained
    )
    with pytest.raises(BrokerAdmissionError) as exc_info:
        ledger.complete_action(owner, routed.action_id, success=success, payload=payload)
    assert exc_info.value.code == "action_result_conflict"


@pytest.mark.parametrize(
    ("success", "failure_reason"),
    [
        (True, "should not be present"),
        (False, None),
    ],
)
def test_event_completed_requires_consistent_outcome_details(success: bool, failure_reason: str | None) -> None:
    with pytest.raises(ValidationError):
        EventCompleted(
            delivery_id="delivery-1",
            lease_id="lease-1",
            success=success,
            failure_reason=failure_reason,
        )


def test_action_owner_resolution_prefers_full_then_longest_and_disconnect_removes_owner() -> None:
    ledger = BrokerLedger()
    source = _session("source", subscriptions=())
    caller = _session("caller")
    limited = _session(
        "limited",
        resources=(ActionResourceDeclaration(kind="message.send", resource_prefix="bot:chat:"),),
    )
    full = _session(
        "full",
        access=BridgeAccess.FULL,
        resources=(ActionResourceDeclaration(kind="message.send", resource_prefix="bot:"),),
    )
    _, delivery_id, lease_id = _active_delivery(ledger, source, caller)
    request = ActionRequest(
        delivery_id=delivery_id,
        lease_id=lease_id,
        correlation_id="call",
        kind="message.send",
        resource_key="bot:chat:1",
    )
    assert ledger.route_action(caller, request, (source, caller, limited, full)).target.bridge_id == "full"
    ledger.disconnect_bridge("full")
    alternate = request.model_copy(update={"correlation_id": "call-2"})
    assert ledger.route_action(caller, alternate, (source, caller, limited)).target.bridge_id == "limited"


def test_action_owner_ties_are_rejected() -> None:
    ledger = BrokerLedger()
    source = _session("source", subscriptions=())
    caller = _session("caller")
    one = _session("one", resources=(ActionResourceDeclaration(kind="x", resource_prefix="a:"),))
    two = _session("two", resources=(ActionResourceDeclaration(kind="x", resource_prefix="a:"),))
    _, delivery_id, lease_id = _active_delivery(ledger, source, caller)
    with pytest.raises(BrokerAdmissionError, match="multiple resource owners"):
        ledger.route_action(
            caller,
            ActionRequest(
                delivery_id=delivery_id,
                lease_id=lease_id,
                correlation_id="tie",
                kind="x",
                resource_key="a:1",
            ),
            (source, caller, one, two),
        )
