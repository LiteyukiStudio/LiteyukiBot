"""Minimal installable B7 broker-peer example."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping

import zmq.asyncio

from liteyukibot.broker import (
    AuthorizationContextWire,
    BridgeAccess,
    BridgeClient,
    BridgeManifest,
    BrokerPeerServer,
    EventAccepted,
    EventCompleted,
    EventIngress,
    RuntimeApiDeclaration,
    RuntimeApiInvoke,
    RuntimeApiResult,
)

BRIDGE_ID = "example.peer"
INSTANCE_TOKEN = "example-peer-token"
API_ID = "experimental.echo"


def build_manifest() -> BridgeManifest:
    """Build the complete manifest owned by this example peer."""

    return BridgeManifest(
        bridge_id=BRIDGE_ID,
        access=BridgeAccess.LIMITED,
        subscriptions=("message.created",),
        runtime_apis=(
            RuntimeApiDeclaration(
                runtime_kind=BRIDGE_ID,
                namespace="experimental",
                operation="echo",
                version="1.0",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string", "minLength": 1}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {"echo": {"type": "string"}},
                    "required": ["echo"],
                    "additionalProperties": False,
                },
            ),
        ),
    )


async def _serve_control(server: BrokerPeerServer) -> None:
    await server.serve_control_once()


async def _serve_business(server: BrokerPeerServer) -> None:
    await server.serve_business_once()


async def run_demo() -> Mapping[str, str]:
    """Run the complete peer lifecycle and return small verification facts."""

    context = zmq.asyncio.Context()
    server = BrokerPeerServer(
        context=context,
        endpoint="tcp://127.0.0.1:*",
        generation=1,
        instance_tokens={BRIDGE_ID: INSTANCE_TOKEN},
    )
    client = BridgeClient(
        context=context,
        endpoints=server.endpoints,
        generation=1,
        identity=b"example-peer",
        manifest=build_manifest(),
        instance_token=INSTANCE_TOKEN,
    )
    try:
        registration = asyncio.create_task(_serve_control(server))
        session_id = await client.register()
        await registration

        ingress = EventIngress(
            source_event_id="example-source-event",
            topic="message.created",
            ordering_key="group:example",
            payload={"bot_id": "bot-1", "message": "hello"},
        )
        business = asyncio.create_task(_serve_business(server))
        await client.send_event_ingress(ingress)
        await business
        delivery = await client.receive_event_message()
        if delivery.event.source_event_id != ingress.source_event_id:
            raise RuntimeError("broker changed the source event identity")

        await client.send_event_accepted(
            EventAccepted(delivery_id=delivery.delivery_id, lease_id=delivery.lease_id)
        )
        await _serve_business(server)

        request = RuntimeApiInvoke(
            delivery_id=delivery.delivery_id,
            source_event_id=delivery.event.source_event_id,
            lease_id=delivery.lease_id,
            correlation_id="example-runtime-call",
            runtime_kind=BRIDGE_ID,
            version="^1.0",
            api_id=API_ID,
            caller_extension_id="example.plugin",
            arguments={"value": "hello"},
            authorization=AuthorizationContextWire(
                event_id=delivery.event.kernel_event_id,
                runtime_id=BRIDGE_ID,
                bot_id="bot-1",
                actor_id="user-1",
            ),
        )
        business = asyncio.create_task(_serve_business(server))
        await client.send_runtime_api_invoke(request)
        await business
        routed_request = await client.receive_business()
        if not isinstance(routed_request, RuntimeApiInvoke) or routed_request.invocation_id is None:
            raise RuntimeError("broker did not route the runtime API invocation")

        result = RuntimeApiResult(
            invocation_id=routed_request.invocation_id,
            correlation_id=routed_request.correlation_id,
            success=True,
            result={"echo": routed_request.arguments["value"]},
        )
        business = asyncio.create_task(_serve_business(server))
        await client.send_runtime_api_result(result)
        await business
        returned_result = await client.receive_business()
        if not isinstance(returned_result, RuntimeApiResult) or returned_result.result != {"echo": "hello"}:
            raise RuntimeError("broker did not return the runtime API result")

        business = asyncio.create_task(_serve_business(server))
        await client.send_event_completed(
            EventCompleted(delivery_id=delivery.delivery_id, lease_id=delivery.lease_id, success=True)
        )
        await business

        unregistration = asyncio.create_task(_serve_control(server))
        await client.unregister()
        await unregistration
        return {"session_id": session_id, "runtime_result": "hello", "shutdown": "true"}
    finally:
        client.close()
        server.close()
        context.term()


def main() -> int:
    print(json.dumps(asyncio.run(run_demo()), sort_keys=True))
    return 0


__all__ = ["API_ID", "BRIDGE_ID", "build_manifest", "main", "run_demo"]
