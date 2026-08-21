"""Reusable bridge-host lifecycle and business-lane coordination."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from jsonschema import Draft202012Validator, ValidationError

from ..events.models import JsonValue
from .peer import BridgeClient, BridgeRegistrationError
from .protocol import AuthorizationContextWire, runtime_version_matches
from .routing import (
    ActionRequest,
    ActionResult,
    BridgeControlInvoke,
    BridgeControlResult,
    EventAccepted,
    EventCompleted,
    EventMessage,
    RuntimeApiInvoke,
    RuntimeApiResult,
    ToolInvoke,
    ToolResult,
)

if TYPE_CHECKING:
    from .business import BrokerBusinessMessage


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    """One action-owner callback outcome to return through the broker."""

    success: bool
    payload: JsonValue = None


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """One stable Tool result; exception text never crosses the broker wire."""

    success: bool
    result: JsonValue = None
    error_code: str | None = None
    error_details: Mapping[str, JsonValue] | None = None


@dataclass(frozen=True, slots=True)
class ControlOutcome:
    """One stable control result; exception text never crosses the broker wire."""

    success: bool
    result: JsonValue = None
    error_code: str | None = None
    error_details: Mapping[str, JsonValue] | None = None


@dataclass(frozen=True, slots=True)
class RuntimeApiOutcome:
    """One stable runtime API result; provider exceptions stay on the bridge."""

    success: bool
    result: JsonValue = None
    error_code: str | None = None
    error_details: Mapping[str, JsonValue] | None = None


type EventHandler = Callable[[BrokerDelivery], Awaitable[None]]
type ActionHandler = Callable[[ActionRequest], Awaitable[ActionOutcome]]
type ToolHandler = Callable[[ToolInvoke], Awaitable[ToolOutcome]]
type ControlHandler = Callable[[BridgeControlInvoke], Awaitable[ControlOutcome]]
type RuntimeApiHandler = Callable[[RuntimeApiInvoke], Awaitable[RuntimeApiOutcome]]


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

    async def request_tool(
        self,
        *,
        correlation_id: str,
        tool_id: str,
        arguments: Mapping[str, JsonValue] | None,
        authorization: AuthorizationContextWire,
        timeout_seconds: float | None = None,
    ) -> ToolResult:
        """Invoke a declared Tool through the active delivery lease."""

        return await self._runner.request_tool(
            delivery_id=self.message.delivery_id,
            lease_id=self.message.lease_id,
            correlation_id=correlation_id,
            tool_id=tool_id,
            arguments=arguments,
            authorization=authorization,
            timeout_seconds=(
                self.message.lease_ttl_ms / 1_000 if timeout_seconds is None else timeout_seconds
            ),
        )

    async def request_control(
        self,
        *,
        correlation_id: str,
        command: str,
        authorization: AuthorizationContextWire,
        payload: Mapping[str, JsonValue] | None = None,
        timeout_seconds: float | None = None,
    ) -> BridgeControlResult:
        """Invoke a declared bridge control through the active delivery lease."""

        return await self._runner.request_control(
            delivery_id=self.message.delivery_id,
            lease_id=self.message.lease_id,
            correlation_id=correlation_id,
            command=command,
            authorization=authorization,
            payload=payload,
            timeout_seconds=(
                self.message.lease_ttl_ms / 1_000 if timeout_seconds is None else timeout_seconds
            ),
        )

    async def request_runtime_api(
        self,
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
    ) -> RuntimeApiResult:
        """Invoke one declared runtime API through the active delivery lease."""

        return await self._runner.request_runtime_api(
            delivery_id=self.message.delivery_id,
            lease_id=self.message.lease_id,
            source_event_id=self.message.event.source_event_id,
            correlation_id=correlation_id,
            runtime_kind=runtime_kind,
            version=version,
            bridge_id=bridge_id,
            api_id=api_id,
            caller_extension_id=caller_extension_id,
            authorization=authorization,
            arguments=arguments,
            timeout_seconds=self.message.lease_ttl_ms / 1_000 if timeout_seconds is None else timeout_seconds,
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
        tool_handlers: Mapping[str, ToolHandler] | None = None,
        control_handlers: Mapping[str, ControlHandler] | None = None,
        runtime_api_handlers: Mapping[str, RuntimeApiHandler] | None = None,
    ) -> None:
        self.client = client
        self._event_handler = event_handler
        self._action_handlers = dict(action_handlers or {})
        self._tool_handlers = dict(tool_handlers or {})
        self._control_handlers = dict(control_handlers or {})
        self._runtime_api_handlers = dict(runtime_api_handlers or {})
        self._pending_results: dict[str, asyncio.Future[ActionResult]] = {}
        self._pending_tool_results: dict[str, asyncio.Future[ToolResult]] = {}
        self._pending_control_results: dict[str, asyncio.Future[BridgeControlResult]] = {}
        self._pending_runtime_api_results: dict[str, asyncio.Future[RuntimeApiResult]] = {}
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
        for tool_future in self._pending_tool_results.values():
            if not tool_future.done():
                tool_future.set_exception(BridgeRegistrationError("bridge runner stopped before Tool result"))
        self._pending_tool_results.clear()
        for control_future in self._pending_control_results.values():
            if not control_future.done():
                control_future.set_exception(BridgeRegistrationError("bridge runner stopped before control result"))
        self._pending_control_results.clear()
        for runtime_api_future in self._pending_runtime_api_results.values():
            if not runtime_api_future.done():
                runtime_api_future.set_exception(
                    BridgeRegistrationError("bridge runner stopped before runtime API result")
                )
        self._pending_runtime_api_results.clear()
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
        elif isinstance(message, ToolInvoke):
            if message.invocation_id is None:
                raise BridgeRegistrationError("broker sent a Tool invocation without an invocation ID")
            self._spawn(self._handle_tool(message))
        elif isinstance(message, BridgeControlInvoke):
            if message.invocation_id is None:
                raise BridgeRegistrationError("broker sent a control invocation without an invocation ID")
            self._spawn(self._handle_control(message))
        elif isinstance(message, RuntimeApiInvoke):
            if message.invocation_id is None:
                raise BridgeRegistrationError("broker sent a runtime API invocation without an invocation ID")
            self._spawn(self._handle_runtime_api(message))
        elif isinstance(message, ToolResult):
            self._resolve_tool_result(message)
        elif isinstance(message, BridgeControlResult):
            self._resolve_control_result(message)
        elif isinstance(message, RuntimeApiResult):
            self._resolve_runtime_api_result(message)
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

    async def request_tool(
        self,
        *,
        delivery_id: str,
        lease_id: str,
        correlation_id: str,
        tool_id: str,
        arguments: Mapping[str, JsonValue] | None,
        authorization: AuthorizationContextWire,
        timeout_seconds: float | None = None,
    ) -> ToolResult:
        normalized_correlation = correlation_id.strip()
        if not normalized_correlation:
            raise ValueError("Tool correlation ID must be non-empty")
        if normalized_correlation in self._pending_tool_results:
            raise BridgeRegistrationError("a Tool result is already pending for this correlation ID")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("Tool timeout must be positive")
        future: asyncio.Future[ToolResult] = asyncio.get_running_loop().create_future()
        self._pending_tool_results[normalized_correlation] = future
        try:
            await self.client.send_tool_invoke(
                ToolInvoke(
                    delivery_id=delivery_id,
                    lease_id=lease_id,
                    correlation_id=normalized_correlation,
                    tool_id=tool_id,
                    arguments=arguments or {},
                    authorization=authorization,
                )
            )
            result = await asyncio.wait_for(future, timeout=timeout_seconds) if timeout_seconds else await future
            if not isinstance(result, ToolResult):
                raise BridgeRegistrationError("received an action result for a pending Tool invocation")
            return result
        finally:
            if self._pending_tool_results.get(normalized_correlation) is future:
                self._pending_tool_results.pop(normalized_correlation, None)

    async def request_control(
        self,
        *,
        delivery_id: str,
        lease_id: str,
        correlation_id: str,
        command: str,
        authorization: AuthorizationContextWire,
        payload: Mapping[str, JsonValue] | None = None,
        timeout_seconds: float | None = None,
    ) -> BridgeControlResult:
        normalized_correlation = correlation_id.strip()
        if not normalized_correlation:
            raise ValueError("control correlation ID must be non-empty")
        if normalized_correlation in self._pending_control_results:
            raise BridgeRegistrationError("a control result is already pending for this correlation ID")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("control timeout must be positive")
        future: asyncio.Future[BridgeControlResult] = asyncio.get_running_loop().create_future()
        self._pending_control_results[normalized_correlation] = future
        try:
            await self.client.send_control_invoke(
                BridgeControlInvoke(
                    delivery_id=delivery_id,
                    lease_id=lease_id,
                    correlation_id=normalized_correlation,
                    command=command,
                    authorization=authorization,
                    payload=payload or {},
                )
            )
            result = await asyncio.wait_for(future, timeout=timeout_seconds) if timeout_seconds else await future
            if not isinstance(result, BridgeControlResult):
                raise BridgeRegistrationError("received an unexpected result for a pending bridge control")
            return result
        finally:
            if self._pending_control_results.get(normalized_correlation) is future:
                self._pending_control_results.pop(normalized_correlation, None)

    async def request_runtime_api(
        self,
        *,
        delivery_id: str,
        lease_id: str,
        source_event_id: str,
        correlation_id: str,
        runtime_kind: str,
        version: str,
        api_id: str,
        caller_extension_id: str,
        authorization: AuthorizationContextWire,
        arguments: Mapping[str, JsonValue] | None = None,
        bridge_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> RuntimeApiResult:
        normalized_correlation = correlation_id.strip()
        if not normalized_correlation:
            raise ValueError("runtime API correlation ID must be non-empty")
        if normalized_correlation in self._pending_runtime_api_results:
            raise BridgeRegistrationError("a runtime API result is already pending for this correlation ID")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("runtime API timeout must be positive")
        future: asyncio.Future[RuntimeApiResult] = asyncio.get_running_loop().create_future()
        self._pending_runtime_api_results[normalized_correlation] = future
        try:
            await self.client.send_runtime_api_invoke(
                RuntimeApiInvoke(
                    delivery_id=delivery_id,
                    source_event_id=source_event_id,
                    lease_id=lease_id,
                    correlation_id=normalized_correlation,
                    runtime_kind=runtime_kind,
                    version=version,
                    bridge_id=bridge_id,
                    api_id=api_id,
                    caller_extension_id=caller_extension_id,
                    arguments=arguments or {},
                    authorization=authorization,
                )
            )
            result = await asyncio.wait_for(future, timeout=timeout_seconds) if timeout_seconds else await future
            if not isinstance(result, RuntimeApiResult):
                raise BridgeRegistrationError("received an unexpected result for a runtime API invocation")
            return result
        finally:
            if self._pending_runtime_api_results.get(normalized_correlation) is future:
                self._pending_runtime_api_results.pop(normalized_correlation, None)

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

    async def _handle_tool(self, request: ToolInvoke) -> None:
        handler = self._tool_handlers.get(request.tool_id)
        if handler is None:
            outcome = ToolOutcome(success=False, error_code="TOOL_NOT_REGISTERED")
        else:
            try:
                outcome = await handler(request)
            except Exception:
                outcome = ToolOutcome(success=False, error_code="TOOL_HANDLER_FAILED")
        await self.client.send_tool_result(
            ToolResult(
                invocation_id=request.invocation_id or "",
                success=outcome.success,
                result=outcome.result,
                error_code=outcome.error_code,
                error_details=outcome.error_details,
            )
        )

    async def _handle_control(self, request: BridgeControlInvoke) -> None:
        handler = self._control_handlers.get(request.command)
        if handler is None:
            outcome = ControlOutcome(success=False, error_code="CONTROL_NOT_REGISTERED")
        else:
            try:
                outcome = await handler(request)
            except Exception:
                outcome = ControlOutcome(success=False, error_code="CONTROL_HANDLER_FAILED")
        await self.client.send_control_result(
            BridgeControlResult(
                invocation_id=request.invocation_id or "",
                success=outcome.success,
                result=outcome.result,
                error_code=outcome.error_code,
                error_details=outcome.error_details,
            )
        )

    async def _handle_runtime_api(self, request: RuntimeApiInvoke) -> None:
        declaration = next(
            (
                item
                for item in self.client.manifest.runtime_apis
                if item.runtime_kind == request.runtime_kind
                and item.api_id == request.api_id
                and runtime_version_matches(request.version, item.version)
            ),
            None,
        )
        handler = self._runtime_api_handlers.get(request.api_id)
        if declaration is None or handler is None:
            outcome = RuntimeApiOutcome(success=False, error_code="RUNTIME_API_NOT_REGISTERED")
        else:
            try:
                Draft202012Validator(dict(declaration.input_schema)).validate(dict(request.arguments))
            except (TypeError, ValueError, ValidationError):
                outcome = RuntimeApiOutcome(success=False, error_code="RUNTIME_API_INVALID_ARGUMENTS")
            else:
                try:
                    outcome = await handler(request)
                    if outcome.success:
                        Draft202012Validator(dict(declaration.output_schema)).validate(outcome.result)
                except (TypeError, ValueError, ValidationError):
                    outcome = RuntimeApiOutcome(success=False, error_code="RUNTIME_API_INVALID_RESULT")
                except Exception:
                    outcome = RuntimeApiOutcome(success=False, error_code="RUNTIME_API_HANDLER_FAILED")
        await self.client.send_runtime_api_result(
            RuntimeApiResult(
                invocation_id=request.invocation_id or "",
                success=outcome.success,
                result=outcome.result,
                error_code=outcome.error_code,
                error_details=outcome.error_details,
            )
        )

    def _resolve_action_result(self, result: ActionResult) -> None:
        if result.correlation_id is None:
            raise BridgeRegistrationError("broker action result is missing its correlation ID")
        future = self._pending_results.get(result.correlation_id)
        if future is not None and not future.done():
            future.set_result(result)

    def _resolve_tool_result(self, result: ToolResult) -> None:
        if result.correlation_id is None:
            raise BridgeRegistrationError("Tool result is missing its correlation ID")
        future = self._pending_tool_results.get(result.correlation_id)
        if future is not None and not future.done():
            future.set_result(result)

    def _resolve_control_result(self, result: BridgeControlResult) -> None:
        if result.correlation_id is None:
            raise BridgeRegistrationError("bridge control result is missing its correlation ID")
        future = self._pending_control_results.get(result.correlation_id)
        if future is not None and not future.done():
            future.set_result(result)

    def _resolve_runtime_api_result(self, result: RuntimeApiResult) -> None:
        if result.correlation_id is None:
            raise BridgeRegistrationError("runtime API result is missing its correlation ID")
        future = self._pending_runtime_api_results.get(result.correlation_id)
        if future is not None and not future.done():
            future.set_result(result)

    def _spawn(self, coroutine: Awaitable[None]) -> None:
        task: asyncio.Task[None] = asyncio.create_task(self._run_background(coroutine))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    @staticmethod
    async def _run_background(coroutine: Awaitable[None]) -> None:
        await coroutine
