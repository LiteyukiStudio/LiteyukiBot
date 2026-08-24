"""Public conformance harness for Native plugins."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .events import ActionEnvelope, ActionExecutor, ActionResult, DispatchResult, EventBus, EventEnvelope
from .logging import get_logger
from .plugins import PluginContext, PluginDefinition, PluginManager
from .services import ServiceKey, ServiceRegistry


class _RecordingActionService:
    """Record actions emitted by one plugin under test."""

    def __init__(self, executor: ActionExecutor | None) -> None:
        """Initialize the recording action service.

        Args:
            executor: Optional action executor used by the harness.

        Returns:
            None.

        Notes:
            This private adapter keeps the public harness independent from an application host.
        """
        self._executor = executor
        self.recorded: list[ActionEnvelope] = []

    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        """Record and optionally execute one action.

        Args:
            action: Action request being processed.
            event: Optional source event.

        Returns:
            The action result from the configured executor.

        Notes:
            Results are validated against the request before being exposed to the plugin under test.
        """
        self.recorded.append(action)
        if self._executor is None or event is None:
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
    """Run one Native plugin against the real v7 lifecycle and EventBus."""

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
            definition: Plugin definition being tested.
            root: Isolated storage root.
            config: Validated plugin configuration.
            dependencies: Services supplied to the plugin.
            action_executor: Optional executor for plugin actions.

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
        """Return the active plugin context.

        Returns:
            The plugin context created by the real manager.
        """
        loaded = self._manager.loaded.get(self.definition.manifest.id)
        if loaded is None or not self._started:
            raise RuntimeError("plugin test harness is not started")
        return loaded.context

    @property
    def recorded_actions(self) -> tuple[ActionEnvelope, ...]:
        """Return actions emitted by the plugin.

        Returns:
            Actions in emission order.
        """
        return tuple(self._actions.recorded)

    def require_service(self, key: ServiceKey) -> Any:
        """Return a service supplied to the harness.

        Args:
            key: Service contract key.

        Returns:
            The registered service value.
        """
        return self._services.require(key)

    async def publish(self, event: EventEnvelope) -> DispatchResult:
        """Publish one event and wait for dispatch.

        Args:
            event: Event associated with the operation.

        Returns:
            The EventBus dispatch result.
        """
        if not self._started:
            raise RuntimeError("plugin test harness is not started")
        return await self._events.publish(event)

    async def start(self) -> None:
        """Start the plugin through the real manager lifecycle.

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
        """Stop the plugin and release harness resources.

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
        """Enter the plugin harness context.

        Returns:
            The started harness.
        """
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        """Exit the plugin harness context.

        Args:
            *_exc_info: Exception context supplied by the async context manager.

        Returns:
            None.
        """
        await self.stop()


__all__ = ["PluginTestHarness"]
