from __future__ import annotations

import asyncio

import pytest
import zmq.asyncio
from pydantic import ValidationError

from liteyukibot.broker import (
    BROKER_ACTION_REQUEST_TYPE_ID,
    ActionRequest,
    ActionResourceDeclaration,
    ActionResult,
    BridgeAccess,
    BridgeClient,
    BridgeManifest,
    BridgeRegistrationError,
    BrokerBusinessWireError,
    BrokerEvent,
    BrokerPeerServer,
    EventAccepted,
    EventCompleted,
    EventIngress,
    EventMessage,
    decode_business_message,
    encode_business_message,
)
from liteyukibot.broker.business import BrokerBusinessMessage
from liteyukibot.lyip import LyipFrame, LyipLane


def _manifest(
    bridge_id: str,
    *,
    subscriptions: tuple[str, ...] = (),
    resources: tuple[ActionResourceDeclaration, ...] = (),
) -> BridgeManifest:
    return BridgeManifest(
        bridge_id=bridge_id,
        access=BridgeAccess.LIMITED,
        subscriptions=subscriptions,
        action_resources=resources,
    )


def _event() -> BrokerEvent:
    return BrokerEvent(
        kernel_event_id="kernel-1",
        source_bridge_id="source",
        source_event_id="platform-1",
        topic="message.created",
        ordering_key="chat:1",
        payload={"text": "hello"},
    )


@pytest.mark.parametrize(
    "message",
    (
        EventIngress(source_event_id="platform-1", topic="message.created", ordering_key="chat:1"),
        EventMessage(delivery_id="delivery-1", lease_id="lease-1", lease_ttl_ms=5_000, event=_event()),
        EventAccepted(delivery_id="delivery-1", lease_id="lease-1"),
        EventCompleted(delivery_id="delivery-1", lease_id="lease-1", success=True),
        ActionRequest(
            delivery_id="delivery-1",
            lease_id="lease-1",
            correlation_id="call-1",
            kind="message.send",
            resource_key="bot:1",
        ),
        ActionResult(action_id="action-1", success=True, payload={"message_id": "1"}),
    ),
)
def test_business_catalog_round_trips_all_messages_without_absolute_deadlines(message: BrokerBusinessMessage) -> None:
    frame = encode_business_message(
        message, generation=1, stream_id="bridge:source:session:business", sequence=0, lease_id="lease-1"
    )

    assert decode_business_message(frame) == message
    assert b"deadline" not in frame.payload
    if isinstance(message, EventMessage):
        assert b"lease_ttl_ms" in frame.payload
    else:
        assert b"lease_ttl_ms" not in frame.payload


def test_business_catalog_rejects_wrong_lane_and_type_id() -> None:
    message = EventIngress(source_event_id="platform-1", topic="message.created", ordering_key="chat:1")
    frame = encode_business_message(
        message, generation=1, stream_id="bridge:source:session:business", sequence=0, lease_id="bridge-business"
    )
    wrong_lane = LyipFrame(
        frame.protocol,
        frame.generation,
        LyipLane.CONTROL,
        frame.type_id,
        frame.stream_id,
        frame.sequence,
        frame.lease_id,
        frame.payload,
    )
    wrong_type = LyipFrame(
        frame.protocol,
        frame.generation,
        LyipLane.BUSINESS,
        BROKER_ACTION_REQUEST_TYPE_ID,
        frame.stream_id,
        frame.sequence,
        frame.lease_id,
        frame.payload,
    )

    with pytest.raises(BrokerBusinessWireError, match="wrong LYIP lane"):
        decode_business_message(wrong_lane)
    with pytest.raises(BrokerBusinessWireError, match="does not match"):
        decode_business_message(wrong_type)


@pytest.mark.parametrize(
    "message",
    (
        EventIngress(source_event_id="platform-1", topic="message.created", ordering_key="chat:1"),
        _event(),
        EventMessage(delivery_id="delivery-1", lease_id="lease-1", lease_ttl_ms=5_000, event=_event()),
        EventAccepted(delivery_id="delivery-1", lease_id="lease-1"),
        EventCompleted(delivery_id="delivery-1", lease_id="lease-1", success=True),
        ActionRequest(
            delivery_id="delivery-1",
            lease_id="lease-1",
            correlation_id="call-1",
            kind="message.send",
            resource_key="bot:1",
        ),
        ActionResult(action_id="action-1", success=True),
    ),
)
def test_business_models_emit_protocol_six_and_reject_protocol_five(message: BrokerBusinessMessage) -> None:
    assert message.protocol == 6
    assert message.model_dump(mode="json")["protocol"] == 6

    with pytest.raises(ValidationError):
        type(message).model_validate({**message.model_dump(mode="json"), "protocol": 5})


async def _register(server: BrokerPeerServer, client: BridgeClient) -> None:
    task = asyncio.create_task(client.register())
    await server.serve_control_once()
    await task


@pytest.mark.asyncio
async def test_zmq_event_lifecycle_action_result_and_stale_lease_validation() -> None:
    context = zmq.asyncio.Context()
    server = BrokerPeerServer(
        context=context,
        endpoint="inproc://broker-business",
        generation=1,
        instance_tokens={"source": "source-token", "target": "target-token", "owner": "owner-token"},
    )
    source = BridgeClient(
        context=context,
        endpoints=server.endpoints,
        generation=1,
        identity=b"source",
        manifest=_manifest("source"),
        instance_token="source-token",
    )
    target = BridgeClient(
        context=context,
        endpoints=server.endpoints,
        generation=1,
        identity=b"target",
        manifest=_manifest("target", subscriptions=("message.created",)),
        instance_token="target-token",
    )
    owner = BridgeClient(
        context=context,
        endpoints=server.endpoints,
        generation=1,
        identity=b"owner",
        manifest=_manifest(
            "owner", resources=(ActionResourceDeclaration(kind="message.send", resource_prefix="bot:"),)
        ),
        instance_token="owner-token",
    )
    try:
        for client in (source, target, owner):
            await _register(server, client)

        await source.send_event_ingress(
            EventIngress(source_event_id="platform-1", topic="message.created", ordering_key="chat:1")
        )
        await server.serve_business_once()
        delivery = await target.receive_event_message()
        assert delivery.attempt == 1
        assert delivery.lease_ttl_ms > 0

        with pytest.raises(BridgeRegistrationError, match="current broker delivery lease"):
            await target.send_event_accepted(EventAccepted(delivery_id=delivery.delivery_id, lease_id="stale"))

        await target.send_event_accepted(EventAccepted(delivery_id=delivery.delivery_id, lease_id=delivery.lease_id))
        await server.serve_business_once()
        await target.send_action_request(
            ActionRequest(
                delivery_id=delivery.delivery_id,
                lease_id=delivery.lease_id,
                correlation_id="call-1",
                kind="message.send",
                resource_key="bot:1",
                payload={"text": "hello"},
            )
        )
        await server.serve_business_once()
        request = await owner.receive_action_request()
        assert request.action_id is not None

        await owner.send_action_result(
            ActionResult(action_id=request.action_id, success=True, payload={"message_id": "7"})
        )
        await server.serve_business_once()
        result = await target.receive_action_result()
        assert result.action_id == request.action_id
        assert result.payload == {"message_id": "7"}

        await target.send_event_completed(
            EventCompleted(delivery_id=delivery.delivery_id, lease_id=delivery.lease_id, success=True)
        )
        await server.serve_business_once()
        snapshot = server.service.ledger.event_snapshot(delivery.event.kernel_event_id)
        assert snapshot.status == "settled"
    finally:
        owner.close()
        target.close()
        source.close()
        server.close()
        context.term()
