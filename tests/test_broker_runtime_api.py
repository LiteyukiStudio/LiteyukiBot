from __future__ import annotations

import asyncio
from collections.abc import Mapping

import pytest
import zmq.asyncio
from liteyukibot_broker import (
    AuthorizationContextWire,
    BridgeAccess,
    BridgeClient,
    BridgeManifest,
    BridgeSession,
    BrokerAdmissionError,
    BrokerBridgeRunner,
    BrokerDelivery,
    BrokerLedger,
    BrokerPeerServer,
    EventIngress,
    RuntimeApiDeclaration,
    RuntimeApiInvoke,
    RuntimeApiOutcome,
)


def _session(
    bridge_id: str,
    *,
    runtime_apis: tuple[RuntimeApiDeclaration, ...] = (),
    subscriptions: tuple[str, ...] = (),
) -> BridgeSession:
    return BridgeSession(
        bridge_id=bridge_id,
        session_id=f"session-{bridge_id}",
        manifest=BridgeManifest(
            bridge_id=bridge_id,
            access=BridgeAccess.LIMITED,
            subscriptions=subscriptions,
            runtime_apis=runtime_apis,
        ),
        peer_identity=f"{bridge_id}-peer".encode(),
    )


def _declaration(version: str = "1.0") -> RuntimeApiDeclaration:
    return RuntimeApiDeclaration(
        runtime_kind="astrbot",
        namespace="event",
        operation="snapshot",
        version=version,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )


def test_broker_routes_runtime_api_to_the_unique_version_compatible_owner() -> None:
    ledger = BrokerLedger()
    source = _session("source")
    caller = _session("kernel", subscriptions=("message.created",))
    owner = _session("astrbot", runtime_apis=(_declaration(),))
    event = ledger.admit_event(
        source,
        EventIngress(
            source_event_id="source-event",
            topic="message.created",
            ordering_key="chat:1",
            payload={"bot_id": "bot-1", "actor": {"id": "actor-1"}},
        ),
        (source, caller, owner),
    )
    delivery = next(
        item for item in ledger.offered_deliveries(event.kernel_event_id) if item.target_bridge_id == "kernel"
    )
    ledger.accept_delivery(caller, delivery.delivery_id, delivery.lease_id)
    ledger.activate_delivery(caller, delivery.delivery_id, delivery.lease_id)
    request = RuntimeApiInvoke(
        delivery_id=delivery.delivery_id,
        source_event_id=event.source_event_id,
        lease_id=delivery.lease_id,
        correlation_id="runtime-call-1",
        runtime_kind="astrbot",
        version="^1.0",
        api_id="event.snapshot",
        caller_extension_id="example.runtime",
        authorization=AuthorizationContextWire(
            event_id=event.kernel_event_id,
            runtime_id="source",
            bot_id="bot-1",
            actor_id="actor-1",
        ),
    )

    routed = ledger.route_runtime_api(caller, request, (source, caller, owner))
    assert routed.target.bridge_id == "astrbot"
    with pytest.raises(BrokerAdmissionError, match="runtime API ownership"):
        ledger.route_runtime_api(
            caller,
            request.model_copy(update={"version": "^2.0", "correlation_id": "runtime-call-2"}),
            (source, caller, owner),
        )


async def _pump_business(server: BrokerPeerServer) -> None:
    while True:
        await server.serve_business_once()


@pytest.mark.asyncio
async def test_runtime_api_runner_round_trip_preserves_source_event_identity() -> None:
    context = zmq.asyncio.Context()
    server = BrokerPeerServer(
        context=context,
        endpoint="inproc://broker-runtime-api",
        generation=1,
        instance_tokens={"source": "source-token", "kernel": "kernel-token", "astrbot": "astrbot-token"},
    )
    completed = asyncio.Event()
    received: list[tuple[str, str]] = []
    broker_task: asyncio.Task[None] | None = None
    caller_task: asyncio.Task[None] | None = None
    owner_task: asyncio.Task[None] | None = None

    async def on_delivery(delivery: BrokerDelivery) -> None:
        result = await delivery.request_runtime_api(
            correlation_id="runtime-round-trip",
            runtime_kind="astrbot",
            version="^1.0",
            api_id="event.snapshot",
            caller_extension_id="example.runtime",
            authorization=AuthorizationContextWire(
                event_id=delivery.message.event.kernel_event_id,
                runtime_id="source",
                bot_id="bot-1",
                actor_id="actor-1",
            ),
        )
        assert result.success
        assert isinstance(result.result, Mapping)
        received.append((str(result.result["source_event_id"]), result.invocation_id))
        completed.set()

    async def provide(request: RuntimeApiInvoke) -> RuntimeApiOutcome:
        assert request.source_event_id == "source-event"
        assert request.version == "^1.0"
        return RuntimeApiOutcome(success=True, result={"source_event_id": request.source_event_id})

    source = BridgeClient(
        context=context,
        endpoints=server.endpoints,
        generation=1,
        identity=b"source",
        manifest=BridgeManifest(bridge_id="source", access=BridgeAccess.LIMITED),
        instance_token="source-token",
    )
    caller = BrokerBridgeRunner(
        BridgeClient(
            context=context,
            endpoints=server.endpoints,
            generation=1,
            identity=b"kernel",
            manifest=BridgeManifest(
                bridge_id="kernel",
                access=BridgeAccess.FULL,
                subscriptions=("message.created",),
            ),
            instance_token="kernel-token",
        ),
        event_handler=on_delivery,
    )
    owner = BrokerBridgeRunner(
        BridgeClient(
            context=context,
            endpoints=server.endpoints,
            generation=1,
            identity=b"astrbot",
            manifest=BridgeManifest(
                bridge_id="astrbot",
                access=BridgeAccess.LIMITED,
                runtime_apis=(_declaration(),),
            ),
            instance_token="astrbot-token",
        ),
        runtime_api_handlers={"event.snapshot": provide},
    )
    try:
        registration = asyncio.create_task(source.register())
        await server.serve_control_once()
        await registration
        for runner in (caller, owner):
            start = asyncio.create_task(runner.start())
            await server.serve_control_once()
            await start
        broker_task = asyncio.create_task(_pump_business(server))
        caller_task = asyncio.create_task(caller.serve_forever())
        owner_task = asyncio.create_task(owner.serve_forever())
        await source.send_event_ingress(
            EventIngress(
                source_event_id="source-event",
                topic="message.created",
                ordering_key="chat:1",
                payload={"bot_id": "bot-1", "actor": {"id": "actor-1"}},
            )
        )
        await asyncio.wait_for(completed.wait(), timeout=1)
        assert received and received[0][0] == "source-event"
    finally:
        for task in (owner_task, caller_task, broker_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in (owner_task, caller_task, broker_task) if task is not None),
            return_exceptions=True,
        )
        owner.close()
        caller.close()
        source.close()
        server.close()
        context.term()
