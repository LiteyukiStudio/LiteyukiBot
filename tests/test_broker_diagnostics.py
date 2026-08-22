from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
import zmq.asyncio

from liteyukibot.broker.diagnostics import BrokerDiagnostics, BrokerDiagnosticsClient, BrokerDiagnosticsError
from liteyukibot.broker.peer import BridgeSession, BrokerPeerServer, BrokerPeerService
from liteyukibot.broker.protocol import (
    ActionResourceDeclaration,
    BridgeAccess,
    BridgeManifest,
    BridgeRejected,
    BrokerDiagnosticsDetail,
    BrokerDiagnosticsList,
    BrokerDiagnosticsStatus,
    decode_broker_message,
    encode_broker_message,
)
from liteyukibot.broker.routing import ActionRequest, BrokerAdmissionError, BrokerLedger, EventIngress
from liteyukibot.lyip import LyipFrame, LyipLane


@dataclass
class Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


def _session(
    bridge_id: str,
    *,
    subscriptions: tuple[str, ...] = ("message.created",),
    resources: tuple[ActionResourceDeclaration, ...] = (),
) -> BridgeSession:
    return BridgeSession(
        bridge_id=bridge_id,
        session_id=f"session-{bridge_id}",
        manifest=BridgeManifest(
            bridge_id=bridge_id,
            access=BridgeAccess.LIMITED,
            subscriptions=subscriptions,
            action_resources=resources,
        ),
        peer_identity=f"{bridge_id}-peer".encode(),
    )


def _ingress(source_event_id: str = "platform-event-77", ordering_key: str = "chat:private-42") -> EventIngress:
    return EventIngress(
        source_event_id=source_event_id,
        topic="message.created",
        ordering_key=ordering_key,
        payload={"text": "private content", "token": "never expose"},
    )


def _control(
    message: BrokerDiagnosticsStatus | BrokerDiagnosticsList | BrokerDiagnosticsDetail,
    sequence: int = 0,
) -> LyipFrame:
    return encode_broker_message(
        message,
        generation=1,
        stream_id="broker:diagnostics:control",
        sequence=sequence,
        lease_id="broker-diagnostics",
    )


def test_diagnostics_require_a_distinct_secret_and_use_the_existing_control_lane() -> None:
    with pytest.raises(ValueError, match="must not reuse"):
        BrokerPeerService(instance_tokens={"source": "shared-token"}, generation=1, diagnostics_token="shared-token")

    service = BrokerPeerService(
        instance_tokens={"source": "bridge-token"}, generation=1, diagnostics_token="diagnostics-token"
    )
    rejected = decode_broker_message(
        service.handle_control(b"local-operator", _control(BrokerDiagnosticsStatus(token="bridge-token")))
    )
    assert isinstance(rejected, BridgeRejected)
    assert rejected.code == "invalid_diagnostics_token"

    accepted = decode_broker_message(
        service.handle_control(
            b"local-operator",
            _control(BrokerDiagnosticsStatus(token="diagnostics-token"), sequence=1),
        )
    )
    assert accepted.type == "broker.diagnostics.status.result"
    assert accepted.terminal_content_bytes == 0
    assert accepted.terminal_content_bytes_capacity == 16 * 1024 * 1024


def test_diagnostics_projection_redacts_payloads_and_tracks_delivery_and_action_timeline() -> None:
    ledger = BrokerLedger()
    diagnostics = BrokerDiagnostics(ledger=ledger, generation=1, token="diagnostics-token")
    source = _session("source", subscriptions=())
    caller = _session("caller")
    owner = _session(
        "owner",
        resources=(ActionResourceDeclaration(kind="message.send", resource_prefix="bot:"),),
    )
    event = ledger.admit_event(source, _ingress(), (source, caller, owner))
    offer = next(item for item in ledger.offered_deliveries(event.kernel_event_id) if item.target_bridge_id == "caller")
    ledger.accept_delivery(caller, offer.delivery_id, offer.lease_id)
    ledger.activate_delivery(caller, offer.delivery_id, offer.lease_id)
    action = ledger.route_action(
        caller,
        ActionRequest(
            delivery_id=offer.delivery_id,
            lease_id=offer.lease_id,
            correlation_id="send-1",
            kind="message.send",
            resource_key="bot:42",
            payload={"message": "secret action payload"},
        ),
        (source, caller, owner),
    )
    ledger.complete_action(owner, action.action_id, success=False, payload={"error": "raw action result"})
    ledger.complete_delivery(
        caller,
        offer.delivery_id,
        offer.lease_id,
        success=False,
        failure_reason="ValueError: secret",
    )

    detail = diagnostics.detail(event.kernel_event_id).model_dump_json()
    assert "private content" not in detail
    assert "never expose" not in detail
    assert "secret action payload" not in detail
    assert "raw action result" not in detail
    assert "platform-event-77" not in detail
    assert "chat:private-42" not in detail
    assert "lease" not in detail
    assert "ValueError" not in detail
    assert "bridge_failed" in detail
    assert '"event.admitted"' in detail
    assert '"delivery.active"' in detail
    assert '"action.routed"' in detail
    assert '"action.completed"' in detail


def test_diagnostics_filters_pages_and_expires_with_the_ledger() -> None:
    clock = Clock()
    ledger = BrokerLedger(terminal_capacity=2, terminal_ttl_seconds=5, monotonic=clock)
    diagnostics = BrokerDiagnostics(ledger=ledger, generation=1, token="diagnostics-token")
    source = _session("source", subscriptions=())
    first = ledger.admit_event(source, _ingress("first", "chat:first"), (source,))
    second = ledger.admit_event(source, _ingress("second", "chat:second"), (source,))

    page = diagnostics.list_events(BrokerDiagnosticsList(token="diagnostics-token", limit=1, topic="message.created"))
    assert len(page.events) == 1
    assert page.next_cursor is not None
    next_page = diagnostics.list_events(
        BrokerDiagnosticsList(token="diagnostics-token", cursor=page.next_cursor, limit=1, source="source")
    )
    assert len(next_page.events) == 1
    assert {page.events[0].event_id, next_page.events[0].event_id} == {first.kernel_event_id, second.kernel_event_id}
    assert diagnostics.list_events(
        BrokerDiagnosticsList(token="diagnostics-token", state="settled", target="missing")
    ).events == ()
    with pytest.raises(ValueError, match="cursor"):
        diagnostics.list_events(BrokerDiagnosticsList(token="diagnostics-token", cursor="forged"))

    clock.now = 6
    assert diagnostics.list_events(BrokerDiagnosticsList(token="diagnostics-token")).events == ()
    with pytest.raises(BrokerAdmissionError, match="not retained"):
        diagnostics.detail(first.kernel_event_id)


@pytest.mark.asyncio
async def test_diagnostics_client_uses_only_the_existing_control_endpoint() -> None:
    context = zmq.asyncio.Context()
    server = BrokerPeerServer(
        context=context,
        endpoint="inproc://broker-diagnostics",
        generation=1,
        instance_tokens={"source": "bridge-token"},
        diagnostics_token="diagnostics-token",
    )
    client = BrokerDiagnosticsClient(
        context=context,
        endpoints=server.endpoints,
        generation=1,
        identity=b"local-operator",
        diagnostics_token="diagnostics-token",
    )
    rejected_client = BrokerDiagnosticsClient(
        context=context,
        endpoints=server.endpoints,
        generation=1,
        identity=b"wrong-local-operator",
        diagnostics_token="wrong-token",
    )
    try:
        assert set(server.endpoints) == {LyipLane.CONTROL, LyipLane.BUSINESS}
        serve = asyncio.create_task(server.serve_control_once())
        status = await client.status()
        await serve
        assert status.generation == 1

        serve = asyncio.create_task(server.serve_control_once())
        with pytest.raises(BrokerDiagnosticsError, match="invalid_diagnostics_token"):
            await rejected_client.status()
        await serve
    finally:
        rejected_client.close()
        client.close()
        server.close()
        context.term()
