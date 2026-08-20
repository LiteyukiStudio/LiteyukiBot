from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import zmq.asyncio
from pydantic import ValidationError

from liteyukibot.app import LiteyukiApp
from liteyukibot.broker import (
    MESSAGE_SEND_KIND,
    ActionOutcome,
    ActionRequest,
    ActionResourceDeclaration,
    AuthorizationContextWire,
    BridgeAccess,
    BridgeClient,
    BridgeControlResult,
    BridgeManifest,
    BrokerBridgeRunner,
    BrokerPeerServer,
    EventIngress,
    KernelBrokerPeer,
    ToolInvoke,
    configured_kernel_bridge,
    parse_message_send_request,
)
from liteyukibot.config import AppSettings
from liteyukibot.events import (
    ActionEnvelope,
    ActionResult,
    ActorRef,
    ConversationRef,
    EventBus,
    EventEnvelope,
    HandlerResult,
    Message,
    Segment,
    SendMessage,
)


def _kernel_settings(
    *,
    access: str = "full",
    subscriptions: tuple[str, ...] = ("message.created",),
    action_resources: tuple[dict[str, str], ...] = (),
) -> AppSettings:
    return AppSettings.model_validate(
        {
            "config_version": 5,
            "broker": {
                "bridges": {
                    "kernel": {
                        "kind": "kernel",
                        "token_secret": "broker.kernel.token",
                        "access": access,
                        "subscriptions": list(subscriptions),
                        "action_resources": list(action_resources),
                    }
                }
            },
        }
    )


def _source_event() -> EventEnvelope:
    return EventEnvelope(
        id="source-event-1",
        runtime_id="nonebot",
        adapter="onebot-v11",
        bot_id="bot-1",
        type="message.group.normal",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=ActorRef(id="user-1"),
        message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
        reply_token="reply-1",
    )


class _FakeLogger:
    def bind(self, **_fields: Any) -> _FakeLogger:
        return self

    def debug(self, _message: str, *_args: Any, **_kwargs: Any) -> None:
        pass

    def info(self, _message: str, *_args: Any, **_kwargs: Any) -> None:
        pass

    def warning(self, _message: str, *_args: Any, **_kwargs: Any) -> None:
        pass

    def error(self, _message: str, *_args: Any, **_kwargs: Any) -> None:
        pass

    def exception(self, _message: str, *_args: Any, **_kwargs: Any) -> None:
        pass


def _unused_tcp_port() -> int:
    for _ in range(100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as first:
            first.bind(("127.0.0.1", 0))
            port = int(first.getsockname()[1])
        if port == 65_535:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as second:
            try:
                second.bind(("127.0.0.1", port + 1))
            except OSError:
                continue
        return port
    pytest.fail("could not find adjacent free TCP ports")


async def _wait_for_settled(server: BrokerPeerServer, event_id: str) -> None:
    for _ in range(100):
        if server.service.ledger.event_snapshot(event_id).status == "settled":
            return
        await asyncio.sleep(0.01)
    pytest.fail("broker did not settle the kernel delivery")


async def _pump_control(server: BrokerPeerServer) -> None:
    while True:
        await server.serve_control_once()


async def _pump_business(server: BrokerPeerServer) -> None:
    while True:
        await server.serve_business_once()


def test_kernel_bridge_requires_full_subscribed_non_owner_manifest() -> None:
    configured = configured_kernel_bridge(_kernel_settings())
    assert configured is not None
    assert configured[0] == "kernel"
    for settings, message in (
        ({"access": "limited"}, "full access"),
        ({"subscriptions": ()}, "at least one subscription"),
        (
            {"action_resources": ({"kind": MESSAGE_SEND_KIND, "resource_prefix": "bot:kernel:"},)},
            "must not declare action ownership",
        ),
    ):
        with pytest.raises(ValidationError, match=message):
            _kernel_settings(**settings)
    with pytest.raises(ValidationError, match="multiple kernel bridges"):
        AppSettings.model_validate(
            {
                "config_version": 5,
                "broker": {
                    "bridges": {
                        "kernel-a": {
                            "kind": "kernel",
                            "token_secret": "broker.kernel-a.token",
                            "access": "full",
                            "subscriptions": ["message.created"],
                        },
                        "kernel-b": {
                            "kind": "kernel",
                            "token_secret": "broker.kernel-b.token",
                            "access": "full",
                            "subscriptions": ["message.created"],
                        },
                    }
                },
            }
        )


def test_app_defers_kernel_peer_creation_until_start() -> None:
    app = LiteyukiApp(_kernel_settings(), logger=_FakeLogger())  # type: ignore[arg-type]

    assert app._configured_kernel_bridge is not None
    assert app._kernel_broker_peer is None


@pytest.mark.asyncio
async def test_kernel_peer_forwards_controls_and_control_handlers() -> None:
    event_bus = EventBus()

    async def select_prompt(_request: Any) -> Any:
        return None

    peer = KernelBrokerPeer.from_settings(
        _kernel_settings(),
        token="kernel-token",
        events=event_bus,
        controls=("agent.prompt.select",),
        control_handlers={"agent.prompt.select": select_prompt},
    )
    try:
        assert peer._runner.client.manifest.controls == ("agent.prompt.select",)
        assert peer._runner._control_handlers == {"agent.prompt.select": select_prompt}
    finally:
        await peer.stop()
        await event_bus.aclose()


@pytest.mark.asyncio
async def test_kernel_peer_request_control_for_tool_reuses_active_delivery_lease_and_authorization() -> None:
    event = _source_event().model_copy(update={"id": "kernel-event-1"})
    authorization = AuthorizationContextWire(
        event_id=event.id,
        runtime_id=event.runtime_id,
        bot_id=event.bot_id,
        actor_id=event.actor.id if event.actor is not None else None,
    )
    request = ToolInvoke(
        delivery_id="agent-delivery-1",
        lease_id="agent-lease-1",
        correlation_id="tool-correlation-1",
        tool_id="tool-1",
        authorization=authorization,
    )
    expected = BridgeControlResult(invocation_id="control-1", success=True, result={"accepted": True})

    class RecordingDelivery:
        message = SimpleNamespace(delivery_id="kernel-delivery-1", lease_id="kernel-lease-1")

        def __init__(self) -> None:
            self.request: dict[str, Any] | None = None

        async def request_control(self, **kwargs: Any) -> BridgeControlResult:
            self.request = kwargs
            return expected

    delivery = RecordingDelivery()
    peer = object.__new__(KernelBrokerPeer)
    peer._active_deliveries = cast(Any, {event.id: delivery})
    peer._active_events = {event.id: event}

    result = await peer.request_control_for_tool(
        request,
        correlation_id="control-correlation-1",
        command="agent.prompt.select",
        payload={"prompt_id": "prompt-1"},
    )

    assert result is expected
    assert delivery.request is not None
    assert delivery.request["authorization"] is authorization
    assert delivery.request["correlation_id"] == "control-correlation-1"
    assert delivery.request["command"] == "agent.prompt.select"
    assert delivery.request["payload"] == {"prompt_id": "prompt-1"}
    assert peer.active_event(event.id) is event

    missing = request.model_copy(
        update={
            "authorization": authorization.model_copy(update={"event_id": "inactive-event"}),
        }
    )
    assert await peer.request_control_for_tool(missing, correlation_id="unused", command="unused") is None


@pytest.mark.asyncio
async def test_kernel_peer_dispatches_native_event_and_routes_send_message_to_source_owner() -> None:
    context = zmq.asyncio.Context()
    server = BrokerPeerServer(
        context=context,
        endpoint="inproc://kernel-peer",
        generation=1,
        instance_tokens={"nonebot": "nonebot-token", "kernel": "kernel-token"},
    )
    peer: KernelBrokerPeer | None = None
    source_owner: BrokerBridgeRunner | None = None
    event_bus: EventBus | None = None
    control_task: asyncio.Task[None] | None = None
    business_task: asyncio.Task[None] | None = None
    owner_task: asyncio.Task[None] | None = None
    seen: list[EventEnvelope] = []
    sent: list[ActionRequest] = []
    action_completed = asyncio.Event()
    try:
        async def owner_action(request: ActionRequest) -> ActionOutcome:
            payload = parse_message_send_request(request, owner_bridge_id="nonebot")
            sent.append(request)
            assert payload.bot_id == "bot-1"
            assert payload.reply_token == "reply-1"
            action_completed.set()
            return ActionOutcome(success=True, payload={"message_id": "native-send-1"})

        source_owner = BrokerBridgeRunner(
            BridgeClient(
                context=context,
                endpoints=server.endpoints,
                generation=1,
                identity=b"nonebot",
                manifest=BridgeManifest(
                    bridge_id="nonebot",
                    access=BridgeAccess.LIMITED,
                    action_resources=(
                        ActionResourceDeclaration(kind=MESSAGE_SEND_KIND, resource_prefix="bot:nonebot:"),
                    ),
                ),
                instance_token="nonebot-token",
            ),
            action_handlers={MESSAGE_SEND_KIND: owner_action},
        )

        async def execute_native_action(event: EventEnvelope, action: ActionEnvelope) -> ActionResult:
            assert peer is not None
            result = await peer.execute_action(event, action)
            assert result is not None
            return result

        event_bus = EventBus(action_executor=execute_native_action)
        kernel_client = BridgeClient(
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
        )
        peer = KernelBrokerPeer("kernel", kernel_client, event_bus)

        async def native_plugin(event: EventEnvelope) -> HandlerResult:
            seen.append(event)
            assert peer is not None
            assert peer.active_event(event.id) is event
            return HandlerResult(
                actions=(
                    ActionEnvelope(
                        action_id="native-send-1",
                        event_id=event.id,
                        runtime_id=event.runtime_id,
                        bot_id=event.bot_id,
                        action=SendMessage(
                            message=Message(segments=(Segment(type="text", data={"text": "pong"}),)),
                            reply_token="reply-1",
                        ),
                    ),
                )
            )

        event_bus.subscribe(native_plugin, name="native-plugin")
        await event_bus.start()
        control_task = asyncio.create_task(_pump_control(server))
        business_task = asyncio.create_task(_pump_business(server))
        await source_owner.start()
        await peer.start()
        owner_task = asyncio.create_task(source_owner.serve_forever())

        event = _source_event()
        await source_owner.client.send_event_ingress(
            EventIngress(
                source_event_id=event.id,
                topic="message.created",
                ordering_key=event.conversation.ordering_key,
                payload=event.model_dump(mode="json"),
            )
        )
        await asyncio.wait_for(action_completed.wait(), timeout=1)
        await _wait_for_settled(server, seen[0].id)

        assert len(seen) == 1
        assert seen[0].id != event.id
        assert seen[0].runtime_id == "nonebot"
        assert [request.kind for request in sent] == [MESSAGE_SEND_KIND]
        assert peer.active_event(seen[0].id) is None
    finally:
        if peer is not None:
            await peer.stop()
        if source_owner is not None:
            await source_owner.stop()
            source_owner.close()
        for task in (owner_task, business_task, control_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in (owner_task, business_task, control_task) if task is not None),
            return_exceptions=True,
        )
        if event_bus is not None:
            await event_bus.aclose()
        server.close()
        context.term()


@pytest.mark.asyncio
async def test_app_lifecycle_registers_kernel_peer_and_dispatches_bridge_ingress(tmp_path: Path) -> None:
    port = _unused_tcp_port()
    endpoint = f"tcp://127.0.0.1:{port}"
    context = zmq.asyncio.Context()
    server = BrokerPeerServer(
        context=context,
        endpoint=endpoint,
        generation=1,
        instance_tokens={"nonebot": "nonebot-token", "kernel": "kernel-token"},
    )
    app: LiteyukiApp | None = None
    source: BridgeClient | None = None
    control_task: asyncio.Task[None] | None = None
    business_task: asyncio.Task[None] | None = None
    seen: list[EventEnvelope] = []
    dispatched = asyncio.Event()
    try:
        settings = AppSettings.model_validate(
            {
                "config_version": 5,
                "core": {"data_dir": str(tmp_path / "data"), "cache_dir": str(tmp_path / "cache")},
                "broker": {
                    "endpoint": endpoint,
                    "bridges": {
                        "kernel": {
                            "kind": "kernel",
                            "token_secret": "broker.kernel.token",
                            "access": "full",
                            "subscriptions": ["message.created"],
                        }
                    },
                },
            }
        )
        app = LiteyukiApp(
            settings,
            logger=_FakeLogger(),  # type: ignore[arg-type]
            runtime_secrets={"broker.kernel.token": "kernel-token"},
        )

        async def native_plugin(event: EventEnvelope) -> HandlerResult:
            seen.append(event)
            dispatched.set()
            return HandlerResult()

        app.events.subscribe(native_plugin, name="native-plugin")
        source = BridgeClient(
            context=context,
            endpoints=server.endpoints,
            generation=1,
            identity=b"nonebot",
            manifest=BridgeManifest(bridge_id="nonebot", access=BridgeAccess.LIMITED),
            instance_token="nonebot-token",
        )
        control_task = asyncio.create_task(_pump_control(server))
        business_task = asyncio.create_task(_pump_business(server))
        await app.start()
        await source.register()

        event = _source_event()
        await source.send_event_ingress(
            EventIngress(
                source_event_id=event.id,
                topic="message.created",
                ordering_key=event.conversation.ordering_key,
                payload=event.model_dump(mode="json"),
            )
        )
        await asyncio.wait_for(dispatched.wait(), timeout=1)

        assert len(seen) == 1
        assert seen[0].id != event.id
        assert seen[0].runtime_id == "nonebot"
        await _wait_for_settled(server, seen[0].id)
    finally:
        if app is not None:
            await app.stop()
        if source is not None:
            await source.unregister()
            source.close()
        for task in (business_task, control_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in (business_task, control_task) if task is not None),
            return_exceptions=True,
        )
        server.close()
        context.term()
