"""Kernel-side full broker peer for native EventBus dispatch."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from urllib.parse import urlparse
from uuid import uuid4

import zmq.asyncio

from ..config.models import AppSettings, BrokerBridgeSettings, configured_kernel_bridge_settings
from ..events import ActionEnvelope, ActionResult, EventBus, EventEnvelope, SendMessage
from ..events.models import JsonValue
from ..lyip import LyipLane
from .actions import MessageSendPayload, make_message_send_request
from .host import BrokerBridgeRunner, BrokerDelivery, ControlHandler, ToolOutcome
from .peer import BridgeClient, BridgeRegistrationError
from .protocol import AuthorizationContextWire, BridgeAccess, BridgeManifest, BrokerToolDeclaration
from .routing import BridgeControlResult, RuntimeApiResult, ToolInvoke


class KernelBridgeError(RuntimeError):
    """Raised when the in-process kernel bridge violates its broker contract."""


def configured_kernel_bridge(settings: AppSettings) -> tuple[str, BrokerBridgeSettings] | None:
    """Return the unique configured in-process kernel bridge, if any."""

    try:
        return configured_kernel_bridge_settings(settings.broker.bridges)
    except ValueError as error:
        raise KernelBridgeError(str(error)) from error


class KernelBrokerPeer:
    """Adapt broker deliveries to the in-process Native Plugin EventBus.

    A broker delivery is bound to its broker-generated event ID only while its
    EventBus dispatch is outstanding. This keeps portable action requests
    lease-scoped even though EventBus runs its FIFO worker in a separate task.
    """

    def __init__(
        self,
        bridge_id: str,
        client: BridgeClient,
        events: EventBus,
        *,
        tool_handlers: Mapping[str, Callable[[ToolInvoke], Awaitable[ToolOutcome]]] | None = None,
        controls: tuple[str, ...] = (),
        control_handlers: Mapping[str, ControlHandler] | None = None,
    ) -> None:
        self.bridge_id = bridge_id
        self._events = events
        self._active_deliveries: dict[str, BrokerDelivery] = {}
        self._active_events: dict[str, EventEnvelope] = {}
        if controls and client.manifest.controls != controls:
            client.manifest = client.manifest.model_copy(update={"controls": controls})
        self._runner = BrokerBridgeRunner(
            client,
            event_handler=self._handle_delivery,
            tool_handlers=tool_handlers,
            control_handlers=control_handlers,
        )
        self._serve_task: asyncio.Task[None] | None = None

    @classmethod
    def from_settings(
        cls,
        settings: AppSettings,
        *,
        token: str,
        events: EventBus,
        tools: tuple[BrokerToolDeclaration, ...] = (),
        tool_handlers: Mapping[str, Callable[[ToolInvoke], Awaitable[ToolOutcome]]] | None = None,
        controls: tuple[str, ...] = (),
        control_handlers: Mapping[str, ControlHandler] | None = None,
    ) -> KernelBrokerPeer:
        configured = configured_kernel_bridge(settings)
        if configured is None:
            raise KernelBridgeError("kernel bridge is not configured")
        bridge_id, bridge = configured
        normalized_token = token.strip()
        if not normalized_token:
            raise KernelBridgeError("kernel bridge token must be non-empty")
        client = BridgeClient(
            context=zmq.asyncio.Context.instance(),
            endpoints=_broker_endpoints(settings.broker.endpoint),
            generation=settings.broker.generation,
            identity=f"kernel:{bridge_id}:{uuid4()}".encode("ascii"),
            manifest=BridgeManifest(
                bridge_id=bridge_id,
                access=BridgeAccess.FULL,
                subscriptions=bridge.subscriptions,
                tools=tools,
                controls=controls,
            ),
            instance_token=normalized_token,
        )
        return cls(
            bridge_id,
            client,
            events,
            tool_handlers=tool_handlers,
            controls=controls,
            control_handlers=control_handlers,
        )

    async def start(self) -> None:
        if self._serve_task is not None:
            raise KernelBridgeError("kernel bridge is already running")
        await self._runner.start()
        self._serve_task = asyncio.create_task(self._runner.serve_forever(), name="liteyuki-kernel-broker")

    async def stop(self) -> None:
        task, self._serve_task = self._serve_task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        try:
            await self._runner.stop()
        finally:
            self._runner.close()

    async def execute_action(self, event: EventEnvelope, action: ActionEnvelope) -> ActionResult | None:
        """Execute one native action through the delivery currently bound to this task.

        ``None`` means that the EventBus dispatch did not originate from this
        broker peer, allowing the application's legacy-independent action path
        to handle locally injected events.
        """

        delivery = self._active_deliveries.get(event.id)
        if delivery is None:
            return None
        if action.event_id != event.id or action.runtime_id != event.runtime_id or action.bot_id != event.bot_id:
            return _action_error(action.action_id, "BROKER_ACTION_PROVENANCE", "action does not match its delivery")
        if not isinstance(action.action, SendMessage):
            return _action_error(
                action.action_id,
                "BROKER_ACTION_UNSUPPORTED",
                "only send_message is portable through the broker in B5",
            )
        request = make_message_send_request(
            delivery_id=delivery.message.delivery_id,
            lease_id=delivery.message.lease_id,
            correlation_id=action.action_id,
            owner_bridge_id=delivery.message.event.source_bridge_id,
            payload=MessageSendPayload(
                bot_id=action.bot_id,
                message=action.action.message,
                conversation=action.action.conversation,
                reply_token=action.action.reply_token,
            ),
        )
        try:
            result = await delivery.request_action(
                correlation_id=request.correlation_id,
                kind=request.kind,
                resource_key=request.resource_key,
                payload=request.payload,
            )
        except (BridgeRegistrationError, TimeoutError, ValueError) as error:
            return _action_error(action.action_id, "BROKER_ACTION_UNAVAILABLE", str(error))
        if result.success:
            return ActionResult(action_id=action.action_id, success=True, data=result.payload)
        return _action_error(action.action_id, "BROKER_ACTION_FAILED", "bridge action owner rejected the request")

    def active_event(self, event_id: str) -> EventEnvelope | None:
        """Return the EventEnvelope currently being dispatched by the kernel peer."""

        return self._active_events.get(event_id)

    async def request_control(
        self,
        event: EventEnvelope,
        *,
        correlation_id: str,
        command: str,
        authorization: AuthorizationContextWire,
        payload: Mapping[str, JsonValue] | None = None,
        timeout_seconds: float | None = None,
    ) -> BridgeControlResult | None:
        """Invoke a bridge control while the native event owns a broker delivery."""

        delivery = self._active_deliveries.get(event.id)
        if delivery is None:
            return None
        if authorization.event_id != event.id:
            raise KernelBridgeError("bridge control authorization does not match the active event")
        return await delivery.request_control(
            correlation_id=correlation_id,
            command=command,
            authorization=authorization,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    async def request_control_for_tool(
        self,
        request: ToolInvoke,
        *,
        correlation_id: str,
        command: str,
        payload: Mapping[str, JsonValue] | None = None,
        timeout_seconds: float | None = None,
    ) -> BridgeControlResult | None:
        """Invoke a control through the active delivery for a Tool authorization event."""

        event = self.active_event(request.authorization.event_id)
        if event is None:
            return None
        return await self.request_control(
            event,
            correlation_id=correlation_id,
            command=command,
            authorization=request.authorization,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    async def request_runtime_api(
        self,
        event: EventEnvelope,
        *,
        correlation_id: str,
        runtime_kind: str,
        version: str,
        api_id: str,
        caller_extension_id: str,
        authorization: AuthorizationContextWire,
        arguments: Mapping[str, JsonValue] | None = None,
        bridge_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> RuntimeApiResult | None:
        """Invoke a runtime API while the native event owns a broker delivery."""

        delivery = self._active_deliveries.get(event.id)
        if delivery is None:
            return None
        if authorization.event_id != event.id:
            raise KernelBridgeError("runtime API authorization does not match the active event")
        return await delivery.request_runtime_api(
            correlation_id=correlation_id,
            runtime_kind=runtime_kind,
            version=version,
            bridge_id=bridge_id,
            api_id=api_id,
            caller_extension_id=caller_extension_id,
            authorization=authorization,
            arguments=arguments,
            timeout_seconds=timeout_seconds,
        )

    async def _handle_delivery(self, delivery: BrokerDelivery) -> None:
        broker_event = delivery.message.event
        try:
            source_event = EventEnvelope.model_validate(broker_event.payload)
        except ValueError as error:
            raise KernelBridgeError("broker delivery payload is not a valid EventEnvelope") from error
        if source_event.id != broker_event.source_event_id:
            raise KernelBridgeError("broker delivery source event identity does not match its payload")
        if source_event.runtime_id != broker_event.source_bridge_id:
            raise KernelBridgeError("broker delivery runtime identity does not match its authenticated source")
        event = source_event.model_copy(
            update={"id": broker_event.kernel_event_id, "runtime_id": broker_event.source_bridge_id}
        )
        self._active_deliveries[event.id] = delivery
        self._active_events[event.id] = event
        try:
            result = await self._events.publish(event)
        finally:
            self._active_deliveries.pop(event.id, None)
            self._active_events.pop(event.id, None)
        if result.status != "processed":
            raise KernelBridgeError(f"native EventBus returned {result.status!r} for broker delivery")


def _broker_endpoints(endpoint: str) -> Mapping[LyipLane, str]:
    """Derive the existing adjacent control/business endpoints from v5 config."""

    parsed = urlparse(endpoint)
    if parsed.scheme != "tcp" or parsed.hostname is None or parsed.port is None:
        raise KernelBridgeError("broker endpoint must be a valid tcp URL")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return {
        LyipLane.CONTROL: f"tcp://{host}:{parsed.port}",
        LyipLane.BUSINESS: f"tcp://{host}:{parsed.port + 1}",
    }


def _action_error(action_id: str, code: str, message: str) -> ActionResult:
    return ActionResult(action_id=action_id, success=False, error_code=code, error_message=message)


__all__ = ["KernelBridgeError", "KernelBrokerPeer", "configured_kernel_bridge"]
