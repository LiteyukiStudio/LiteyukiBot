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
    AuthorizationContextWire,
    BridgeAccess,
    BridgeClient,
    BridgeControlInvoke,
    BridgeControlResult,
    BridgeManifest,
    BridgeRegistrationError,
    BridgeSession,
    BrokerAdmissionError,
    BrokerBusinessWireError,
    BrokerEvent,
    BrokerPeerServer,
    BrokerPeerService,
    BrokerToolDeclaration,
    BusinessDispatch,
    EventAccepted,
    EventCompleted,
    EventIngress,
    EventMessage,
    ToolInvoke,
    ToolResult,
    decode_business_message,
    encode_business_message,
)
from liteyukibot.broker.business import BrokerBusinessMessage
from liteyukibot.lyip import LyipFrame, LyipLane, LyipOfferResult


def _manifest(
    bridge_id: str,
    *,
    subscriptions: tuple[str, ...] = (),
    resources: tuple[ActionResourceDeclaration, ...] = (),
    tools: tuple[BrokerToolDeclaration, ...] = (),
    controls: tuple[str, ...] = (),
) -> BridgeManifest:
    return BridgeManifest(
        bridge_id=bridge_id,
        access=BridgeAccess.LIMITED,
        subscriptions=subscriptions,
        action_resources=resources,
        tools=tools,
        controls=controls,
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
        ToolInvoke(
            delivery_id="delivery-1",
            lease_id="lease-1",
            correlation_id="tool-call-1",
            tool_id="owner.echo",
            authorization=AuthorizationContextWire(event_id="event-1", runtime_id="source", bot_id="bot-1"),
        ),
        ToolResult(invocation_id="invocation-1", success=False, error_code="DENIED"),
        BridgeControlInvoke(
            delivery_id="delivery-1",
            lease_id="lease-1",
            correlation_id="control-call-1",
            command="agent.history.clear",
            authorization=AuthorizationContextWire(event_id="event-1", runtime_id="source", bot_id="bot-1"),
            payload={"conversation_id": "chat:1"},
        ),
        BridgeControlResult(invocation_id="control-invocation-1", success=True, result={"cleared": 2}),
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
        ToolInvoke(
            delivery_id="delivery-1",
            lease_id="lease-1",
            correlation_id="tool-call-1",
            tool_id="owner.echo",
            authorization=AuthorizationContextWire(event_id="event-1", runtime_id="source", bot_id="bot-1"),
        ),
        ToolResult(invocation_id="invocation-1", success=False, error_code="DENIED"),
        BridgeControlInvoke(
            delivery_id="delivery-1",
            lease_id="lease-1",
            correlation_id="control-call-1",
            command="agent.history.clear",
            authorization=AuthorizationContextWire(event_id="event-1", runtime_id="source", bot_id="bot-1"),
        ),
        BridgeControlResult(invocation_id="control-invocation-1", success=False, error_code="DENIED"),
    ),
)
def test_business_models_emit_protocol_seven_and_reject_protocol_six(message: BrokerBusinessMessage) -> None:
    assert message.protocol == 7
    assert message.model_dump(mode="json")["protocol"] == 7

    with pytest.raises(ValidationError):
        type(message).model_validate({**message.model_dump(mode="json"), "protocol": 6})


def test_duplicate_action_request_does_not_redispatch_owner_and_replays_retained_result() -> None:
    service = BrokerPeerService(
        instance_tokens={"source": "source-token", "caller": "caller-token", "owner": "owner-token"},
        generation=1,
    )
    source = BridgeSession("source", "source-session", _manifest("source"), b"source")
    caller = BridgeSession(
        "caller",
        "caller-session",
        _manifest("caller", subscriptions=("message.created",)),
        b"caller",
    )
    owner = BridgeSession(
        "owner",
        "owner-session",
        _manifest("owner", resources=(ActionResourceDeclaration(kind="message.send", resource_prefix="bot:"),)),
        b"owner",
    )
    for session in (source, caller, owner):
        service._sessions_by_bridge[session.bridge_id] = session
        service._sessions_by_identity[session.peer_identity] = session
    event = service.admit_event(
        source.peer_identity,
        EventIngress(source_event_id="platform-1", topic="message.created", ordering_key="chat:1"),
    )
    offer = service.ledger.offered_deliveries(event.kernel_event_id)[0]
    service.ledger.accept_delivery(caller, offer.delivery_id, offer.lease_id)
    service.ledger.activate_delivery(caller, offer.delivery_id, offer.lease_id)
    request = ActionRequest(
        delivery_id=offer.delivery_id,
        lease_id=offer.lease_id,
        correlation_id="call-1",
        kind="message.send",
        resource_key="bot:1",
    )
    request_frame = encode_business_message(
        request,
        generation=1,
        stream_id="bridge:caller:caller-session:action",
        sequence=0,
        lease_id=offer.lease_id,
    )
    first = service.handle_business(caller.peer_identity, request_frame)
    assert len(first) == 1
    dispatched_request = first[0].message
    assert isinstance(dispatched_request, ActionRequest)
    assert dispatched_request.action_id is not None
    assert service.handle_business(caller.peer_identity, request_frame) == ()

    result_frame = encode_business_message(
        ActionResult(action_id=dispatched_request.action_id, success=True, payload={"message_id": "7"}),
        generation=1,
        stream_id="bridge:owner:owner-session:action",
        sequence=0,
        lease_id="bridge-business",
    )
    assert len(service.handle_business(owner.peer_identity, result_frame)) == 1
    replay = service.handle_business(caller.peer_identity, request_frame)
    assert len(replay) == 1
    assert replay[0].target == caller
    assert replay[0].message == ActionResult(
        action_id=dispatched_request.action_id,
        correlation_id="call-1",
        success=True,
        payload={"message_id": "7"},
    )


def test_control_request_routes_to_declared_owner_and_replays_retained_result() -> None:
    service = BrokerPeerService(
        instance_tokens={"source": "source-token", "caller": "caller-token", "agent": "agent-token"},
        generation=1,
    )
    source = BridgeSession("source", "source-session", _manifest("source"), b"source")
    caller = BridgeSession(
        "caller",
        "caller-session",
        _manifest("caller", subscriptions=("message.created",)),
        b"caller",
    )
    agent = BridgeSession(
        "agent",
        "agent-session",
        _manifest("agent", controls=("agent.history.clear",)),
        b"agent",
    )
    for session in (source, caller, agent):
        service._sessions_by_bridge[session.bridge_id] = session
        service._sessions_by_identity[session.peer_identity] = session
    event = service.admit_event(
        source.peer_identity,
        EventIngress(source_event_id="platform-1", topic="message.created", ordering_key="chat:1"),
    )
    offer = service.ledger.offered_deliveries(event.kernel_event_id)[0]
    service.ledger.accept_delivery(caller, offer.delivery_id, offer.lease_id)
    service.ledger.activate_delivery(caller, offer.delivery_id, offer.lease_id)
    request = BridgeControlInvoke(
        delivery_id=offer.delivery_id,
        lease_id=offer.lease_id,
        correlation_id="control-call-1",
        command="agent.history.clear",
        authorization=AuthorizationContextWire(
            event_id=event.kernel_event_id,
            runtime_id="source",
            bot_id="bot-1",
            actor_id="user-1",
        ),
        payload={"conversation_id": "chat:1"},
    )
    request_frame = encode_business_message(
        request,
        generation=1,
        stream_id="bridge:caller:caller-session:control",
        sequence=0,
        lease_id=offer.lease_id,
    )
    first = service.handle_business(caller.peer_identity, request_frame)
    assert len(first) == 1
    dispatched = first[0].message
    assert isinstance(dispatched, BridgeControlInvoke)
    assert dispatched.invocation_id is not None
    assert first[0].target == agent

    result_frame = encode_business_message(
        BridgeControlResult(
            invocation_id=dispatched.invocation_id,
            success=True,
            result={"cleared": 2},
        ),
        generation=1,
        stream_id="bridge:agent:agent-session:control",
        sequence=0,
        lease_id="bridge-business",
    )
    result_dispatch = service.handle_business(agent.peer_identity, result_frame)
    assert result_dispatch == (
        BusinessDispatch(
            target=caller,
            message=BridgeControlResult(
                invocation_id=dispatched.invocation_id,
                correlation_id="control-call-1",
                success=True,
                result={"cleared": 2},
            ),
        ),
    )
    replay = service.handle_business(caller.peer_identity, request_frame)
    assert replay == result_dispatch

    conflict = request.model_copy(update={"payload": {"conversation_id": "other"}})
    conflict_frame = encode_business_message(
        conflict,
        generation=1,
        stream_id="bridge:caller:caller-session:control",
        sequence=1,
        lease_id=offer.lease_id,
    )
    with pytest.raises(BrokerAdmissionError, match="different control content"):
        service.handle_business(caller.peer_identity, conflict_frame)

    authorization_mismatch = request.model_copy(
        update={
            "correlation_id": "control-call-runtime-mismatch",
            "authorization": request.authorization.model_copy(update={"runtime_id": "other"}),
        }
    )
    authorization_frame = encode_business_message(
        authorization_mismatch,
        generation=1,
        stream_id="bridge:caller:caller-session:control",
        sequence=2,
        lease_id=offer.lease_id,
    )
    with pytest.raises(BrokerAdmissionError, match="authorization"):
        service.handle_business(caller.peer_identity, authorization_frame)


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

        # The same correlation is idempotent: it neither re-dispatches the owner nor changes the action ID.
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
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(owner.receive_action_request(), timeout=0.05)

        await owner.send_action_result(
            ActionResult(action_id=request.action_id, success=True, payload={"message_id": "7"})
        )
        await server.serve_business_once()
        result = await target.receive_action_result()
        assert result.action_id == request.action_id
        assert result.payload == {"message_id": "7"}

        # Once settled, the duplicate receives the retained result without another owner dispatch.
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
        replay = await target.receive_action_result()
        assert replay == result

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


def test_tool_invoke_routes_to_declared_owner_and_replays_retained_result() -> None:
    service = BrokerPeerService(
        instance_tokens={"source": "source-token", "caller": "caller-token", "owner": "owner-token"},
        generation=1,
    )
    source = BridgeSession("source", "source-session", _manifest("source"), b"source")
    caller = BridgeSession(
        "caller", "caller-session", _manifest("caller", subscriptions=("message.created",)), b"caller"
    )
    owner = BridgeSession(
        "owner",
        "owner-session",
        _manifest(
            "owner",
            tools=(
                BrokerToolDeclaration(
                    id="owner.echo",
                    description="Echo",
                    input_schema={"type": "object"},
                    output_schema={"type": "object"},
                ),
            ),
        ),
        b"owner",
    )
    for session in (source, caller, owner):
        service._sessions_by_bridge[session.bridge_id] = session
        service._sessions_by_identity[session.peer_identity] = session
    event = service.admit_event(
        source.peer_identity,
        EventIngress(source_event_id="platform-1", topic="message.created", ordering_key="chat:1"),
    )
    offer = service.ledger.offered_deliveries(event.kernel_event_id)[0]
    service.ledger.accept_delivery(caller, offer.delivery_id, offer.lease_id)
    service.ledger.activate_delivery(caller, offer.delivery_id, offer.lease_id)
    request = ToolInvoke(
        delivery_id=offer.delivery_id,
        lease_id=offer.lease_id,
        correlation_id="tool-call-1",
        tool_id="owner.echo",
        arguments={"message": "hello"},
        authorization=AuthorizationContextWire(event_id=event.kernel_event_id, runtime_id="source", bot_id="bot-1"),
    )
    frame = encode_business_message(
        request,
        generation=1,
        stream_id="bridge:caller:caller-session:tool",
        sequence=0,
        lease_id=offer.lease_id,
    )
    first = service.handle_business(caller.peer_identity, frame)
    assert len(first) == 1
    invocation = first[0].message
    assert isinstance(invocation, ToolInvoke)
    assert invocation.invocation_id is not None
    assert first[0].target is owner

    result = ToolResult(invocation_id=invocation.invocation_id, success=False, error_code="DENIED")
    result_frame = encode_business_message(
        result,
        generation=1,
        stream_id="bridge:owner:owner-session:tool",
        sequence=0,
        lease_id="bridge-business",
    )
    completed = service.handle_business(owner.peer_identity, result_frame)
    expected = result.model_copy(update={"correlation_id": "tool-call-1"})
    assert completed == (BusinessDispatch(target=caller, message=expected),)
    assert service.handle_business(caller.peer_identity, frame) == (BusinessDispatch(target=caller, message=expected),)


@pytest.mark.asyncio
async def test_business_pump_discards_invalid_frames_and_continues() -> None:
    context = zmq.asyncio.Context()
    server = BrokerPeerServer(
        context=context,
        endpoint="inproc://broker-business-pump",
        generation=1,
        instance_tokens={"source": "source-token"},
    )
    source = BridgeClient(
        context=context,
        endpoints=server.endpoints,
        generation=1,
        identity=b"source",
        manifest=_manifest("source"),
        instance_token="source-token",
    )
    try:
        await _register(server, source)
        malformed = LyipFrame(
            1,
            1,
            LyipLane.BUSINESS,
            999,
            source.business_stream_id("malformed"),
            0,
            "broker-business",
            b"{}",
        )
        assert await source._dealer.offer(malformed) is LyipOfferResult.ACCEPTED
        assert await server.serve_business_once() is None

        admission_failure = encode_business_message(
            EventAccepted(delivery_id="missing", lease_id="lease"),
            generation=1,
            stream_id=source.business_stream_id("delivery"),
            sequence=0,
            lease_id="lease",
        )
        assert await source._dealer.offer(admission_failure) is LyipOfferResult.ACCEPTED
        assert await server.serve_business_once() is None

        await source.send_event_ingress(
            EventIngress(source_event_id="platform-1", topic="message.created", ordering_key="chat:1")
        )
        assert await server.serve_business_once() is not None
    finally:
        source.close()
        server.close()
        context.term()
