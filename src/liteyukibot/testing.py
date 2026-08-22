"""Public conformance harnesses for plugins and child runtimes."""

from __future__ import annotations

import asyncio
import inspect
import tempfile
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from .events import (
    ActionEnvelope,
    ActionExecutor,
    ActionResult,
    DispatchResult,
    EventBus,
    EventEnvelope,
)
from .logging import get_logger
from .plugins import PluginContext, PluginDefinition, PluginManager
from .runtime import (
    ActionResponse,
    EventAccepted,
    ProtocolVersion,
    RuntimeSpec,
    RuntimeState,
    RuntimeSupervisor,
)
from .runtime.protocol import EventCompleted, JsonValue, json_mapping
from .runtime.supervisor import ActionProvenance, ActionSinkResult, EventSink
from .services import ServiceKey, ServiceRegistry


class _RecordingActionService:
    """Represent the recording action service contract."""
    def __init__(self, executor: ActionExecutor | None) -> None:
        """Initialize the recording action service.

        Args:
            executor: The executor value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_RecordingActionService.__init__`. It performs the local
            state transition directly and is not a stable extension boundary.
        """
        self._executor = executor
        self.recorded: list[ActionEnvelope] = []

    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        """Execute one request through the recording action service.

        Args:
            action: Action request being processed.
            event: Event associated with the operation.

        Returns:
            The `ActionResult` result produced by the operation.

        Notes:
            Internal implementation detail for `_RecordingActionService.execute`. It delegates to `append`,
            `_executor`, `isawaitable` while keeping intermediate state local to the owning operation.
        """
        self.recorded.append(action)
        if self._executor is None:
            return ActionResult(action_id=action.action_id, success=True)
        if event is None:
            return ActionResult(action_id=action.action_id, success=True)
        result = self._executor(event, action)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, ActionResult):
            raise TypeError(f"expected ActionResult, got {type(result).__name__}")
        if result.action_id != action.action_id:
            raise ValueError("action result correlation id does not match the action")
        return result


class PluginTestHarness:
    """Run one native plugin against the real v7 lifecycle and event bus."""

    def __init__(
        self,
        definition: PluginDefinition,
        *,
        root: Path,
        config: Mapping[str, Any] | None = None,
        dependencies: Mapping[ServiceKey, Any] | None = None,
        action_executor: ActionExecutor | None = None,
    ) -> None:
        """Initialize the plugin test harness.

        Args:
            definition: The definition value used by the operation.
            root: The root value used by the operation.
            config: Validated configuration used by the operation.
            dependencies: The dependencies value used by the operation.
            action_executor: Executor that routes actions to the owning runtime.

        Returns:
            None.
        """
        self.definition = definition
        self.root = Path(root)
        self._services = ServiceRegistry()
        for key, value in (dependencies or {}).items():
            self._services.provide(key, value, provider="liteyukibot.testing")
        self._actions = _RecordingActionService(action_executor)
        self._events = EventBus(
            action_executor=lambda event, action: self._actions.execute(action, event=event),
            logger=get_logger(component="plugin-test"),
        )
        self._manager = PluginManager(
            services=self._services,
            events=self._events,
            actions=self._actions,
            logger=get_logger(component="plugin-test"),
            data_dir=self.root / "data",
            cache_dir=self.root / "cache",
        )
        self._config = dict(config or {})
        self._started = False
        self._closed = False

    @property
    def context(self) -> PluginContext:
        """Return the plugin test harness's context.

        Returns:
            The `PluginContext` result produced by the operation.
        """
        loaded = self._manager.loaded.get(self.definition.manifest.id)
        if loaded is None or not self._started:
            raise RuntimeError("plugin test harness is not started")
        return loaded.context

    @property
    def recorded_actions(self) -> tuple[ActionEnvelope, ...]:
        """Return the plugin test harness's recorded actions.

        Returns:
            The `tuple[ActionEnvelope, ...]` result produced by the operation.
        """
        return tuple(self._actions.recorded)

    def require_service(self, key: ServiceKey) -> Any:
        """Return service, failing when it is unavailable.

        Args:
            key: Stable FIFO ordering key for the queued work.

        Returns:
            The requested `Any` value.
        """
        return self._services.require(key)

    async def publish(self, event: EventEnvelope) -> DispatchResult:
        """Publish one event and wait for its dispatch result.

        Args:
            event: Event associated with the operation.

        Returns:
            The `DispatchResult` result produced by the operation.
        """
        if not self._started:
            raise RuntimeError("plugin test harness is not started")
        return await self._events.publish(event)

    async def start(self) -> None:
        """Start the plugin test harness.

        Returns:
            None.
        """
        if self._closed:
            raise RuntimeError("plugin test harness is single-use")
        if self._started:
            raise RuntimeError("plugin test harness is already started")
        await self._events.start()
        try:
            await self._manager.setup(
                {self.definition.manifest.id: self.definition},
                {self.definition.manifest.id: self._config},
            )
            await self._manager.start()
        except BaseException:
            try:
                if self._manager.loaded:
                    await self._manager.stop()
            finally:
                await self._events.aclose()
                self._closed = True
            raise
        self._started = True

    async def stop(self) -> None:
        """Stop the plugin test harness and release its owned resources.

        Returns:
            None.
        """
        if self._closed:
            return
        self._closed = True
        if not self._started:
            await self._events.aclose()
            return
        self._started = False
        errors: list[BaseException] = []
        try:
            await self._manager.stop()
        except BaseException as error:
            errors.append(error)
        try:
            await self._events.aclose()
        except BaseException as error:
            errors.append(error)
        if errors:
            raise BaseExceptionGroup("plugin test harness shutdown failed", errors)

    async def __aenter__(self) -> PluginTestHarness:
        """Enter the plugin test harness context.

        Returns:
            The `PluginTestHarness` result produced by the operation.
        """
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        """Exit the plugin test harness context.

        Args:
            *_exc_info: Exception context supplied by the asynchronous context manager.

        Returns:
            None.
        """
        await self.stop()


class RuntimeTestHarness:
    """Run one custom child against a real RuntimeSupervisor."""

    def __init__(
        self,
        spec: RuntimeSpec,
        *,
        event_sink: EventSink | None = None,
        action_sink: Callable[[str, dict[str, JsonValue]], Awaitable[ActionSinkResult]] | None = None,
    ) -> None:
        """Initialize the runtime test harness.

        Args:
            spec: The spec value used by the operation.
            event_sink: The event sink value used by the operation.
            action_sink: The action sink value used by the operation.

        Returns:
            None.
        """
        if spec.command is None or not spec.command:
            raise ValueError("runtime test harness requires an explicit child command")
        self._state_directory = tempfile.TemporaryDirectory(prefix="liteyuki-runtime-test-")
        self.spec = replace(
            spec,
            env={**spec.env, "LITEYUKI_RUNTIME_STATE_DIR": self._state_directory.name},
        )
        self._event_sink = event_sink
        self._action_sink = action_sink
        self._child_events: list[tuple[str, dict[str, JsonValue]]] = []
        self._child_actions: list[tuple[str, dict[str, JsonValue]]] = []
        self._child_output: deque[tuple[str, str]] = deque(maxlen=100)
        self._delivery_completions: dict[str, EventCompleted] = {}
        self._delivery_completion_condition = asyncio.Condition()
        self._supervisor = RuntimeSupervisor(
            logger=get_logger(component="runtime-test"),
            event_sink=self._record_event,
            action_sink=self._record_action,
            output_sink=self._record_output,
            delivery_completion_sink=self._record_delivery_completion,
        )
        self._supervisor.add(self.spec)
        self._started = False
        self._closed = False

    @property
    def state(self) -> RuntimeState:
        """Return the runtime test harness's state.

        Returns:
            The `RuntimeState` result produced by the operation.
        """
        return self._supervisor.records[self.spec.id].state

    @property
    def protocol_version(self) -> ProtocolVersion | None:
        """Return the runtime test harness's protocol version.

        Returns:
            The `ProtocolVersion | None` result produced by the operation.
        """
        return self._supervisor.records[self.spec.id].protocol_version

    @property
    def capabilities(self) -> frozenset[str]:
        """Return the runtime test harness's capabilities.

        Returns:
            The `frozenset[str]` result produced by the operation.
        """
        return self._supervisor.records[self.spec.id].capabilities

    @property
    def child_events(self) -> tuple[tuple[str, Mapping[str, JsonValue]], ...]:
        """Return the runtime test harness's child events.

        Returns:
            The `tuple[tuple[str, Mapping[str, JsonValue]], ...]` result produced by the operation.
        """
        return tuple(
            (runtime_id, json_mapping(payload))
            for runtime_id, payload in self._child_events
        )

    @property
    def child_actions(self) -> tuple[tuple[str, Mapping[str, JsonValue]], ...]:
        """Return the runtime test harness's child actions.

        Returns:
            The `tuple[tuple[str, Mapping[str, JsonValue]], ...]` result produced by the operation.
        """
        return tuple(
            (runtime_id, json_mapping(payload))
            for runtime_id, payload in self._child_actions
        )

    @property
    def child_output(self) -> tuple[tuple[str, str], ...]:
        """Return the runtime test harness's child output.

        Returns:
            The `tuple[tuple[str, str], ...]` result produced by the operation.
        """
        return tuple(self._child_output)

    def diagnostics(self) -> str:
        """Implement the diagnostics operation for the runtime test harness.

        Returns:
            The `str` result produced by the operation.
        """
        health = self._supervisor.health()[self.spec.id]
        output = "\n".join(f"[{channel}] {line}" for channel, line in self._child_output)
        return f"runtime health: {health}\nchild output:\n{output or '<none>'}"

    async def start(self) -> None:
        """Start the runtime test harness.

        Returns:
            None.
        """
        if self._closed:
            raise RuntimeError("runtime test harness is single-use")
        if self._started:
            raise RuntimeError("runtime test harness is already started")
        try:
            await self._supervisor.start()
        except BaseException:
            self._closed = True
            self._state_directory.cleanup()
            raise
        self._started = True

    async def stop(self) -> None:
        """Stop the runtime test harness and release its owned resources.

        Returns:
            None.
        """
        if self._closed:
            return
        self._closed = True
        if self._started:
            self._started = False
            await self._supervisor.stop()
        self._state_directory.cleanup()

    async def dispatch_event(
        self,
        payload: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> EventAccepted:
        """Dispatch event.

        Args:
            payload: JSON-safe payload carried by the operation.
            correlation_id: Stable identifier for the correlation.
            timeout_seconds: Maximum duration to wait, in seconds.

        Returns:
            The `EventAccepted` result produced by the operation.
        """
        if not self._started:
            raise RuntimeError("runtime test harness is not started")
        return await self._supervisor.dispatch_event(
            self.spec.id,
            correlation_id or str(uuid4()),
            payload,
            timeout_seconds,
        )

    async def execute_action(
        self,
        payload: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> ActionResponse:
        """Execute action.

        Args:
            payload: JSON-safe payload carried by the operation.
            correlation_id: Stable identifier for the correlation.
            timeout_seconds: Maximum duration to wait, in seconds.

        Returns:
            The `ActionResponse` result produced by the operation.
        """
        if not self._started:
            raise RuntimeError("runtime test harness is not started")
        return await self._supervisor.execute_action(
            self.spec.id,
            correlation_id or str(uuid4()),
            payload,
            timeout_seconds,
        )

    async def wait_for_delivery_completion(self, correlation_id: str, *, timeout_seconds: float) -> EventCompleted:
        """Wait for for delivery completion.

        Args:
            correlation_id: Stable identifier for the correlation.
            timeout_seconds: Maximum duration to wait, in seconds.

        Returns:
            The `EventCompleted` result produced by the operation.
        """
        if not self._started:
            raise RuntimeError("runtime test harness is not started")
        try:
            async with asyncio.timeout(timeout_seconds):
                async with self._delivery_completion_condition:
                    await self._delivery_completion_condition.wait_for(
                        lambda: correlation_id in self._delivery_completions
                    )
                    return self._delivery_completions[correlation_id]
        except TimeoutError as error:
            raise TimeoutError(
                f"runtime delivery {correlation_id} did not complete within {timeout_seconds:.1f}s\n"
                f"{self.diagnostics()}"
            ) from error

    async def _record_event(self, runtime_id: str, payload: dict[str, JsonValue]) -> str:
        """Record event.

        Args:
            runtime_id: Stable runtime identifier.
            payload: JSON-safe payload carried by the operation.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `RuntimeTestHarness._record_event`. It delegates to `append`,
            `json_mapping`, `_event_sink` while keeping intermediate state local to the owning operation.
        """
        self._child_events.append((runtime_id, json_mapping(payload)))
        if self._event_sink is None:
            return "accepted"
        return await self._event_sink(runtime_id, payload)

    async def _record_action(
        self,
        runtime_id: str,
        payload: dict[str, JsonValue],
        _provenance: ActionProvenance | None,
    ) -> ActionSinkResult:
        """Record action.

        Args:
            runtime_id: Stable runtime identifier.
            payload: JSON-safe payload carried by the operation.
            _provenance: The provenance value used by the operation.

        Returns:
            The `ActionSinkResult` result produced by the operation.

        Notes:
            Internal implementation detail for `RuntimeTestHarness._record_action`. It delegates to
            `append`, `json_mapping`, `_action_sink` while keeping intermediate state local to the owning
            operation.
        """
        self._child_actions.append((runtime_id, json_mapping(payload)))
        if self._action_sink is None:
            return ActionSinkResult(ok=True, data={"recorded": True})
        return await self._action_sink(runtime_id, payload)

    def _record_output(self, _runtime_id: str, channel: str, line: str) -> None:
        """Record output.

        Args:
            _runtime_id: Stable identifier for the runtime.
            channel: The channel value used by the operation.
            line: The line value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `RuntimeTestHarness._record_output`. It delegates to `append`
            while keeping intermediate state local to the owning operation.
        """
        self._child_output.append((channel, line))

    async def _record_delivery_completion(self, _runtime_id: str, message: EventCompleted) -> None:
        """Record delivery completion.

        Args:
            _runtime_id: Stable identifier for the runtime.
            message: Message content associated with the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `RuntimeTestHarness._record_delivery_completion`. It
            delegates to `notify_all` while keeping intermediate state local to the owning operation.
        """
        async with self._delivery_completion_condition:
            self._delivery_completions[message.correlation_id] = message
            self._delivery_completion_condition.notify_all()

    async def __aenter__(self) -> RuntimeTestHarness:
        """Enter the runtime test harness context.

        Returns:
            The `RuntimeTestHarness` result produced by the operation.
        """
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        """Exit the runtime test harness context.

        Args:
            *_exc_info: Exception context supplied by the asynchronous context manager.

        Returns:
            None.
        """
        await self.stop()


__all__ = ["PluginTestHarness", "RuntimeTestHarness"]
