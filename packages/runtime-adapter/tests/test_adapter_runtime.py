from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import cast

import pytest
from liteyukibot_broker import (
    BridgeSupportGrade,
    BrokerBridgeRunner,
    EventIngress,
    MessageSendPayload,
    make_message_send_request,
)
from liteyukibot_runtime_adapter import bridge_definition
from liteyukibot_runtime_adapter.contracts import AdapterConnection, AdapterContext, AdapterPlugin
from liteyukibot_runtime_adapter.host import AdapterHost, _adapter_manifest

from liteyukibot.config.models import BrokerActionResourceSettings
from liteyukibot.events import ConversationRef, EventEnvelope, Message


class FakeClient:
    def __init__(self) -> None:
        self.events: list[EventIngress] = []

    async def send_event_ingress(self, message: EventIngress) -> None:
        self.events.append(message)


class FakeRunner:
    def __init__(self) -> None:
        self.client = FakeClient()

    async def serve_forever(self) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.emitter: object | None = None
        self.messages: list[MessageSendPayload] = []
        self.closed = False

    async def start(self, emit: object) -> None:
        self.emitter = emit

    async def send_message(self, payload: MessageSendPayload) -> str:
        self.messages.append(payload)
        return "sent"

    async def close(self) -> None:
        self.closed = True

    async def wait_failure(self) -> None:
        await asyncio.Future()


def _plugin(connection: FakeConnection) -> AdapterPlugin:
    async def create(_context: AdapterContext) -> AdapterConnection:
        return connection

    return AdapterPlugin(
        kind="onebot-v11",
        distribution="example-driver",
        grade=BridgeSupportGrade.STABLE,
        create=create,
    )


def test_adapter_bridge_declares_mixed_support() -> None:
    definition = bridge_definition()

    assert definition.kind == "adapter"
    assert definition.grade is BridgeSupportGrade.MIXED
    assert definition.distribution == "liteyukibot-v7-runtime-adapter"


@pytest.mark.asyncio
async def test_adapter_host_routes_owned_events_and_exact_message_send() -> None:
    runner = FakeRunner()
    connection = FakeConnection()
    host = AdapterHost(cast(BrokerBridgeRunner, runner), "adapter", {"onebot-v11": _plugin(connection)})
    await host.start({"adapters": {"main": {"kind": "onebot-v11", "bot_id": "bot", "config": {}}}})

    event = EventEnvelope(
        id="event-1",
        runtime_id="adapter",
        adapter="onebot-v11",
        bot_id="bot",
        type="message.private.normal",
        conversation=ConversationRef(id="conversation", type="private"),
        message=Message(),
        raw={"platform": "onebot"},
    )
    await host.emit("bot", event)
    payload = MessageSendPayload(
        bot_id="bot",
        message=Message(),
        conversation=ConversationRef(id="conversation", type="private"),
    )
    outcome = await host.execute(
        make_message_send_request(
            delivery_id="delivery-1",
            lease_id="lease-1",
            correlation_id="action-1",
            owner_bridge_id="adapter",
            payload=payload,
        )
    )

    assert runner.client.events[0].topic == "onebot.v11.message.private"
    assert runner.client.events[0].ordering_key == "bot:private:conversation"
    assert runner.client.events[0].payload["raw"] == {"platform": "onebot"}
    assert outcome.success
    assert outcome.payload == "sent"
    assert connection.messages == [payload]
    await host.close()
    assert connection.closed


def test_adapter_manifest_requires_exact_configured_bot_resources() -> None:
    adapters: Mapping[str, Mapping[str, object]] = {
        "main": {"kind": "onebot-v11", "bot_id": "bot", "config": {}},
    }
    manifest = _adapter_manifest(
        "adapter",
        "limited",
        (),
        (BrokerActionResourceSettings(kind="message.send", resource="bot:adapter:bot"),),
        adapters,
    )

    assert manifest.access.value == "limited"
    assert manifest.subscriptions == ()
    assert manifest.action_resources[0].resource == "bot:adapter:bot"

    with pytest.raises(RuntimeError, match="exactly match"):
        _adapter_manifest(
            "adapter",
            "limited",
            (),
            (BrokerActionResourceSettings(kind="message.send", resource_prefix="bot:adapter:"),),
            adapters,
        )
