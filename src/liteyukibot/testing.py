"""Public conformance harnesses for plugins and child runtimes."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
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
from .runtime.protocol import JsonValue, json_mapping
from .runtime.supervisor import ActionProvenance, ActionSinkResult, EventSink
from .services import ServiceKey, ServiceRegistry


class _RecordingActionService:
    def __init__(self, executor: ActionExecutor | None) -> None:
        self._executor = executor
        self.recorded: list[ActionEnvelope] = []

    async def execute(self, action: ActionEnvelope) -> ActionResult:
        self.recorded.append(action)
        if self._executor is None:
            return ActionResult(action_id=action.action_id, success=True)
        result = self._executor(action)
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
        self.definition = definition
        self.root = Path(root)
        self._services = ServiceRegistry()
        for key, value in (dependencies or {}).items():
            self._services.provide(key, value, provider="liteyukibot.testing")
        self._actions = _RecordingActionService(action_executor)
        self._events = EventBus(
            action_executor=self._actions.execute,
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
        loaded = self._manager.loaded.get(self.definition.manifest.id)
        if loaded is None or not self._started:
            raise RuntimeError("plugin test harness is not started")
        return loaded.context

    @property
    def recorded_actions(self) -> tuple[ActionEnvelope, ...]:
        return tuple(self._actions.recorded)

    def require_service(self, key: ServiceKey) -> Any:
        return self._services.require(key)

    async def publish(self, event: EventEnvelope) -> DispatchResult:
        if not self._started:
            raise RuntimeError("plugin test harness is not started")
        return await self._events.publish(event)

    async def start(self) -> None:
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
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
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
        if spec.command is None or not spec.command:
            raise ValueError("runtime test harness requires an explicit child command")
        self.spec = spec
        self._event_sink = event_sink
        self._action_sink = action_sink
        self._child_events: list[tuple[str, dict[str, JsonValue]]] = []
        self._child_actions: list[tuple[str, dict[str, JsonValue]]] = []
        self._supervisor = RuntimeSupervisor(
            logger=get_logger(component="runtime-test"),
            event_sink=self._record_event,
            action_sink=self._record_action,
        )
        self._supervisor.add(spec)
        self._started = False
        self._closed = False

    @property
    def state(self) -> RuntimeState:
        return self._supervisor.records[self.spec.id].state

    @property
    def protocol_version(self) -> ProtocolVersion | None:
        return self._supervisor.records[self.spec.id].protocol_version

    @property
    def capabilities(self) -> frozenset[str]:
        return self._supervisor.records[self.spec.id].capabilities

    @property
    def child_events(self) -> tuple[tuple[str, Mapping[str, JsonValue]], ...]:
        return tuple(
            (runtime_id, json_mapping(payload))
            for runtime_id, payload in self._child_events
        )

    @property
    def child_actions(self) -> tuple[tuple[str, Mapping[str, JsonValue]], ...]:
        return tuple(
            (runtime_id, json_mapping(payload))
            for runtime_id, payload in self._child_actions
        )

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("runtime test harness is single-use")
        if self._started:
            raise RuntimeError("runtime test harness is already started")
        try:
            await self._supervisor.start()
        except BaseException:
            self._closed = True
            raise
        self._started = True

    async def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._started:
            self._started = False
            await self._supervisor.stop()

    async def dispatch_event(
        self,
        payload: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> EventAccepted:
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
        if not self._started:
            raise RuntimeError("runtime test harness is not started")
        return await self._supervisor.execute_action(
            self.spec.id,
            correlation_id or str(uuid4()),
            payload,
            timeout_seconds,
        )

    async def _record_event(self, runtime_id: str, payload: dict[str, JsonValue]) -> str:
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
        self._child_actions.append((runtime_id, json_mapping(payload)))
        if self._action_sink is None:
            return ActionSinkResult(ok=True, data={"recorded": True})
        return await self._action_sink(runtime_id, payload)

    async def __aenter__(self) -> RuntimeTestHarness:
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.stop()


__all__ = ["PluginTestHarness", "RuntimeTestHarness"]
