from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import cast

import pytest
import zmq.asyncio
from liteyukibot_broker import (
    MESSAGE_SEND_KIND,
    ActionOutcome,
    ActionRequest,
    ActionResourceDeclaration,
    BridgeAccess,
    BridgeClient,
    BridgeManifest,
    BrokerBridgeRunner,
    BrokerDelivery,
    BrokerPeerServer,
    EventIngress,
    MessageSendPayload,
    make_message_send_request,
    message_send_resource_key,
    parse_message_send_request,
)
from pydantic import ValidationError

from liteyukibot.events.models import ConversationRef, Message, Segment


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


async def _start(server: BrokerPeerServer, runner: BrokerBridgeRunner) -> None:
    task = asyncio.create_task(runner.start())
    await server.serve_control_once()
    await task


async def _pump_business(server: BrokerPeerServer) -> None:
    while True:
        await server.serve_business_once()


def test_message_send_contract_binds_payload_to_the_owner_scoped_resource() -> None:
    payload = MessageSendPayload(
        bot_id=" bot-1 ",
        message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
        conversation=ConversationRef(id=" room-1 ", type="group"),
    )

    request = make_message_send_request(
        delivery_id="delivery-1",
        lease_id="lease-1",
        correlation_id="call-1",
        owner_bridge_id=" nonebot ",
        payload=payload,
    )

    assert request.kind == MESSAGE_SEND_KIND
    assert request.resource_key == "bot:nonebot:bot-1"
    assert message_send_resource_key("nonebot", "bot-1") == request.resource_key
    assert parse_message_send_request(request, owner_bridge_id="nonebot") == payload
    with pytest.raises(ValueError, match="resource key"):
        parse_message_send_request(request, owner_bridge_id="another-owner")
    with pytest.raises(ValidationError, match="conversation or reply_token"):
        MessageSendPayload(bot_id="bot-1", message=payload.message)


@pytest.mark.asyncio
async def test_runner_correlates_concurrent_action_results_and_completes_delivery() -> None:
    context = zmq.asyncio.Context()
    server = BrokerPeerServer(
        context=context,
        endpoint="inproc://broker-host-runner",
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
    completed = asyncio.Event()
    received: dict[str, int] = {}
    delivered_event_ids: list[str] = []

    async def on_delivery(delivery: BrokerDelivery) -> None:
        delivered_event_ids.append(delivery.message.event.kernel_event_id)
        first, second = await asyncio.gather(
            delivery.request_action(
                correlation_id="first",
                kind="echo",
                resource_key="owner:echo",
                payload={"number": 1},
            ),
            delivery.request_action(
                correlation_id="second",
                kind="echo",
                resource_key="owner:echo",
                payload={"number": 2},
            ),
        )
        assert first.correlation_id == "first"
        assert second.correlation_id == "second"
        assert isinstance(first.payload, Mapping)
        assert isinstance(second.payload, Mapping)
        received["first"] = first.payload["number"]  # type: ignore[assignment]
        received["second"] = second.payload["number"]  # type: ignore[assignment]
        completed.set()

    async def echo(request: ActionRequest) -> ActionOutcome:
        return ActionOutcome(success=True, payload=request.payload)

    target = BrokerBridgeRunner(
        BridgeClient(
            context=context,
            endpoints=server.endpoints,
            generation=1,
            identity=b"target",
            manifest=_manifest("target", subscriptions=("message.created",)),
            instance_token="target-token",
        ),
        event_handler=on_delivery,
    )
    owner = BrokerBridgeRunner(
        BridgeClient(
            context=context,
            endpoints=server.endpoints,
            generation=1,
            identity=b"owner",
            manifest=_manifest(
                "owner",
                resources=(ActionResourceDeclaration(kind="echo", resource_prefix="owner:"),),
            ),
            instance_token="owner-token",
        ),
        action_handlers={"echo": echo},
    )
    broker_task: asyncio.Task[None] | None = None
    target_task: asyncio.Task[None] | None = None
    owner_task: asyncio.Task[None] | None = None
    try:
        source_register = asyncio.create_task(source.register())
        await server.serve_control_once()
        await source_register
        await _start(server, target)
        await _start(server, owner)
        broker_task = asyncio.create_task(_pump_business(server))
        target_task = asyncio.create_task(target.serve_forever())
        owner_task = asyncio.create_task(owner.serve_forever())

        await source.send_event_ingress(
            EventIngress(source_event_id="platform-1", topic="message.created", ordering_key="chat:1")
        )
        await asyncio.wait_for(completed.wait(), timeout=1)
        await asyncio.sleep(0.01)

        assert received == {"first": 1, "second": 2}
        assert server.service.ledger.event_snapshot(delivered_event_ids[0]).status == "settled"
    finally:
        for task in (owner_task, target_task, broker_task):
            if task is not None:
                task.cancel()
        pending_tasks = tuple(task for task in (owner_task, target_task, broker_task) if task is not None)
        await asyncio.gather(*pending_tasks, return_exceptions=True)
        owner.close()
        target.close()
        source.close()
        server.close()
        context.term()


@pytest.mark.asyncio
async def test_runner_expires_an_unresolved_delivery_scoped_action() -> None:
    class PendingClient:
        async def send_action_request(self, _request: ActionRequest) -> None:
            return None

    runner = BrokerBridgeRunner(cast(BridgeClient, PendingClient()))

    with pytest.raises(TimeoutError):
        await runner.request_action(
            delivery_id="delivery-1",
            lease_id="lease-1",
            correlation_id="action-1",
            kind="message.send",
            resource_key="bot:source:bot-1",
            timeout_seconds=0.01,
        )

    assert not runner._pending_results
