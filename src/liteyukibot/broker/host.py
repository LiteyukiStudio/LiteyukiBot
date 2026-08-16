"""Reusable bridge-host lifecycle and business-lane coordination."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..events.models import JsonValue
from .peer import BridgeClient, BridgeRegistrationError
from .routing import ActionRequest, ActionResult, EventAccepted, EventCompleted, EventMessage

if TYPE_CHECKING:
    from .business import BrokerBusinessMessage


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    """One action-owner callback outcome to return through the broker."""

    success: bool
    payload: JsonValue = None


type EventHandler = Callable[[BrokerDelivery], Awaitable[None]]
type ActionHandler = Callable[[ActionRequest], Awaitable[ActionOutcome]]


@dataclass(frozen=True, slots=True)
class BrokerDelivery:
    """An active delivery exposed to one bridge event handler."""

    _runner: BrokerBridgeRunner
    message: EventMessage

    async def request_action(
        self,
        *,
        correlation_id: str,
        kind: str,
        resource_key: str,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> ActionResult:
        """Route an action for this delivery and await its correlated result."""

        return await self._runner.request_action(
            delivery_id=self.message.delivery_id,
            lease_id=self.message.lease_id,
            correlation_id=correlation_id,
            kind=kind,
            resource_key=resource_key,
            payload=payload,
            timeout_seconds=self.message.lease_ttl_ms / 1_000,
        )


class BrokerBridgeRunner:
    """Coordinate a bridge host over one registered :class:`BridgeClient`.

    The embedding framework owns its event loop and repeatedly calls
    :meth:`serve_once` (or starts :meth:`serve_forever`). This class deliberately
    does not create framework processes or make retry/replay promises.
    """

    def __init__(
        self,
        client: BridgeClient,
        *,
        event_handler: EventHandler | None = None,
        action_handlers: Mapping[str, ActionHandler] | None = None,
    ) -> None:
        self.client = client
        self._event_handler = event_handler
        self._action_handlers = dict(action_handlers or {})
        self._pending_results: dict[str, asyncio.Future[ActionResult]] = {}
        self._background: set[asyncio.Task[None]] = set()
        self._closing = False

    async def start(self) -> str:
        """Register this bridge and return its broker-assigned session ID."""

        if self._closing:
            raise BridgeRegistrationError("bridge runner is closing")
        return await self.client.register()

    async def stop(self) -> None:
        """Cancel local work and explicitly unregister a live bridge session."""

        self._closing = True
        current = asyncio.current_task()
        tasks = tuple(task for task in self._background if task is not current)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background.difference_update(tasks)
        for future in self._pending_results.values():
            if not future.done():
                future.set_exception(BridgeRegistrationError("bridge runner stopped before action result"))
        self._pending_results.clear()
        if self.client.session_id is not None:
            await self.client.unregister()

    def close(self) -> None:
        """Close ZMQ resources after :meth:`stop` has completed or on fatal exit."""

        self._closing = True
        self.client.close()

    async def serve_forever(self) -> None:
        """Dispatch broker business traffic until cancelled or explicitly stopped."""

        while not self._closing:
            await self.serve_once()

    async def serve_once(self) -> BrokerBusinessMessage:
        """Receive one broker message and schedule its corresponding local work."""

        message = await self.client.receive_business()
        if isinstance(message, EventMessage):
            self._spawn(self._handle_delivery(message))
        elif isinstance(message, ActionRequest):
            if message.action_id is None:
                raise BridgeRegistrationError("broker action request is missing its action ID")
            self._spawn(self._handle_action(message))
        elif isinstance(message, ActionResult):
            self._resolve_action_result(message)
        else:
            raise BridgeRegistrationError(f"broker sent unsupported host message {message.type!r}")
        return message

    async def request_action(
        self,
        *,
        delivery_id: str,
        lease_id: str,
        correlation_id: str,
        kind: str,
        resource_key: str,
        payload: Mapping[str, JsonValue] | None = None,
        timeout_seconds: float | None = None,
    ) -> ActionResult:
        """Send one active-delivery action and await its exact correlation result."""

        normalized_correlation = correlation_id.strip()
        if not normalized_correlation:
            raise ValueError("action correlation ID must be non-empty")
        if normalized_correlation in self._pending_results:
            raise BridgeRegistrationError("an action result is already pending for this correlation ID")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("action timeout must be positive")
        future: asyncio.Future[ActionResult] = asyncio.get_running_loop().create_future()
        self._pending_results[normalized_correlation] = future
        try:
            await self.client.send_action_request(
                ActionRequest(
                    delivery_id=delivery_id,
                    lease_id=lease_id,
                    correlation_id=normalized_correlation,
                    kind=kind,
                    resource_key=resource_key,
                    payload=payload or {},
                )
            )
            if timeout_seconds is None:
                result = await future
            else:
                result = await asyncio.wait_for(future, timeout=timeout_seconds)
            return result
        finally:
            if self._pending_results.get(normalized_correlation) is future:
                self._pending_results.pop(normalized_correlation, None)

    async def _handle_delivery(self, message: EventMessage) -> None:
        await self.client.send_event_accepted(EventAccepted(delivery_id=message.delivery_id, lease_id=message.lease_id))
        try:
            if self._event_handler is None:
                raise BridgeRegistrationError("bridge received an event delivery without an event handler")
            await self._event_handler(BrokerDelivery(self, message))
        except Exception as error:
            await self.client.send_event_completed(
                EventCompleted(
                    delivery_id=message.delivery_id,
                    lease_id=message.lease_id,
                    success=False,
                    failure_reason=f"{type(error).__name__}: {error}",
                )
            )
        else:
            await self.client.send_event_completed(
                EventCompleted(delivery_id=message.delivery_id, lease_id=message.lease_id, success=True)
            )

    async def _handle_action(self, request: ActionRequest) -> None:
        handler = self._action_handlers.get(request.kind)
        if handler is None:
            outcome = ActionOutcome(success=False, payload={"error": "unsupported_action"})
        else:
            try:
                outcome = await handler(request)
            except Exception as error:
                outcome = ActionOutcome(
                    success=False,
                    payload={"error": "action_handler_failed", "message": f"{type(error).__name__}: {error}"},
                )
        await self.client.send_action_result(
            ActionResult(action_id=request.action_id or "", success=outcome.success, payload=outcome.payload)
        )

    def _resolve_action_result(self, result: ActionResult) -> None:
        if result.correlation_id is None:
            raise BridgeRegistrationError("broker action result is missing its correlation ID")
        future = self._pending_results.get(result.correlation_id)
        if future is not None and not future.done():
            future.set_result(result)

    def _spawn(self, coroutine: Awaitable[None]) -> None:
        task: asyncio.Task[None] = asyncio.create_task(self._run_background(coroutine))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    @staticmethod
    async def _run_background(coroutine: Awaitable[None]) -> None:
        await coroutine
