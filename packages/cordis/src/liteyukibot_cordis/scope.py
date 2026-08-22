"""Scoped dynamic providers and owned lifecycle cleanup."""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Awaitable, Callable, Hashable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import uuid4

from liteyukibot.runtime_api import (
    RuntimeContextFactory,
    RuntimeRequirement,
    RuntimeResolver,
    runtime_handler,
    validate_runtime_bindings,
)

from .audit import CordisAuditService

type Provider = Callable[[Scope], Any] | Callable[[], Any]
type Disposer = Callable[[], Awaitable[None] | None]


class RegistrationSink(Protocol):
    """Define the structural interface required from a registration sink."""
    def register(self, scope: Scope, kind: str, value: object) -> Disposer:
        """Register the registration sink operation.

        Args:
            scope: The scope value used by the operation.
            kind: The kind value used by the operation.
            value: Value to validate, transform, or store.

        Returns:
            The `Disposer` result produced by the operation.
        """
        ...


@dataclass(frozen=True, slots=True)
class UnavailableProviderError(LookupError):
    """Raised when the unavailable provider contract cannot be satisfied."""
    key: Hashable

    def __str__(self) -> str:
        """Implement the str operation for the unavailable provider error.

        Returns:
            The `str` result produced by the operation.
        """
        return f"Cordis provider {self.key!r} is unavailable"


class ProviderCycleError(RuntimeError):
    """Raised when the provider cycle contract cannot be satisfied."""
    pass


class Scope:
    """A tree-owned resource scope with lazy providers and deterministic close."""

    def __init__(
        self,
        *,
        plugin_id: str,
        config: Mapping[str, object] | None = None,
        parent: Scope | None = None,
        sink: RegistrationSink | None = None,
        audit: CordisAuditService | None = None,
        runtime_context_factory: Callable[[str], RuntimeContextFactory] | None = None,
        runtime_resolver: RuntimeResolver | None = None,
        runtime_requirements: tuple[RuntimeRequirement, ...] = (),
    ) -> None:
        """Initialize the scope.

        Args:
            plugin_id: Stable identifier for the plugin.
            config: Validated configuration used by the operation.
            parent: The parent value used by the operation.
            sink: The sink value used by the operation.
            audit: The audit value used by the operation.
            runtime_context_factory: The runtime context factory value used by the operation.
            runtime_resolver: The runtime resolver value used by the operation.
            runtime_requirements: The runtime requirements value used by the operation.

        Returns:
            None.
        """
        self.id = str(uuid4())
        self.plugin_id = plugin_id
        self.config: Mapping[str, object] = (
            config if config is not None else parent.config if parent is not None else {}
        )
        self.parent = parent
        self._sink: RegistrationSink | None = sink if sink is not None else parent._sink if parent is not None else None
        self._audit: CordisAuditService = (
            audit if audit is not None else parent._audit if parent is not None else CordisAuditService()
        )
        self._runtime_context_factory_factory: Callable[[str], RuntimeContextFactory] | None = (
            runtime_context_factory
            if runtime_context_factory is not None
            else parent._runtime_context_factory_factory
            if parent is not None
            else None
        )
        self._runtime_resolver = runtime_resolver
        if self._runtime_resolver is None and parent is not None:
            self._runtime_resolver = parent._runtime_resolver
        self._runtime_requirements: tuple[RuntimeRequirement, ...] = runtime_requirements or (
            parent._runtime_requirements if parent is not None else ()
        )
        self._providers: dict[Hashable, Provider] = {}
        self._instances: dict[Hashable, object] = {}
        self._resolving: list[Hashable] = []
        self._disposers: list[Disposer] = []
        self._children: list[Scope] = []
        self._closed = False
        if parent is not None:
            parent._children.append(self)

    @property
    def closed(self) -> bool:
        """Return the scope's closed.

        Returns:
            Whether the requested condition is satisfied.
        """
        return self._closed

    def child(
        self,
        *,
        plugin_id: str | None = None,
        config: Mapping[str, object] | None = None,
        runtime_requirements: tuple[RuntimeRequirement, ...] = (),
    ) -> Scope:
        """Implement the child operation for the scope.

        Args:
            plugin_id: Stable identifier for the plugin.
            config: Validated configuration used by the operation.
            runtime_requirements: The runtime requirements value used by the operation.

        Returns:
            The `Scope` result produced by the operation.
        """
        self._ensure_open()
        return Scope(
            plugin_id=plugin_id or self.plugin_id,
            config=config,
            parent=self,
            runtime_requirements=runtime_requirements,
        )

    def provide(self, key: Hashable, provider: Provider) -> None:
        """Implement the provide operation for the scope.

        Args:
            key: Stable FIFO ordering key for the queued work.
            provider: The provider value used by the operation.

        Returns:
            None.
        """
        self._ensure_open()
        if key in self._providers:
            raise ValueError(f"Cordis provider {key!r} is already registered in this scope")
        self._providers[key] = provider

    def own(self, disposer: Disposer) -> None:
        """Implement the own operation for the scope.

        Args:
            disposer: The disposer value used by the operation.

        Returns:
            None.
        """
        self._ensure_open()
        self._disposers.append(disposer)

    async def use(self, key: Hashable) -> object:
        """Implement the use operation for the scope.

        Args:
            key: Stable FIFO ordering key for the queued work.

        Returns:
            The `object` result produced by the operation.
        """
        owner = self._find_provider_owner(key)
        if owner is None:
            raise UnavailableProviderError(key)
        return await owner._resolve(key)

    async def _resolve(self, key: Hashable) -> object:
        """Resolve the scope operation.

        Args:
            key: Stable FIFO ordering key for the queued work.

        Returns:
            The `object` result produced by the operation.

        Notes:
            Internal implementation detail for `Scope._resolve`. It delegates to `join`, `repr`,
            `_ensure_open`, `append` while keeping intermediate state local to the owning operation.
        """
        if key in self._instances:
            return self._instances[key]
        if key in self._resolving:
            chain = " -> ".join(repr(item) for item in (*self._resolving, key))
            raise ProviderCycleError(f"Cordis provider dependency cycle: {chain}")
        self._ensure_open()
        provider = self._providers[key]
        self._resolving.append(key)
        try:
            value = self._call_provider(provider)
            if inspect.isawaitable(value):
                value = await value
            self._instances[key] = value
            disposer = _resource_disposer(value)
            if disposer is not None:
                self._disposers.append(disposer)
            self._audit.record(
                plugin_id=self.plugin_id,
                scope_id=self.id,
                event_id=None,
                operation="provider.activate",
                outcome="ok",
            )
            return value
        finally:
            self._resolving.pop()

    def _call_provider(self, provider: Provider) -> object:
        """Implement the call provider operation for the scope.

        Args:
            provider: The provider value used by the operation.

        Returns:
            The `object` result produced by the operation.

        Notes:
            Internal implementation detail for `Scope._call_provider`. It delegates to `signature`,
            `provider` while keeping intermediate state local to the owning operation.
        """
        try:
            parameters = inspect.signature(provider).parameters
        except TypeError, ValueError:
            return provider()  # type: ignore[call-arg]
        return provider(self) if parameters else provider()  # type: ignore[call-arg]

    def _find_provider_owner(self, key: Hashable) -> Scope | None:
        """Implement the find provider owner operation for the scope.

        Args:
            key: Stable FIFO ordering key for the queued work.

        Returns:
            The `Scope | None` result produced by the operation.

        Notes:
            Internal implementation detail for `Scope._find_provider_owner`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        scope: Scope | None = self
        while scope is not None:
            if key in scope._providers:
                return scope
            scope = scope.parent
        return None

    def _register(self, kind: str, value: object) -> None:
        """Register the scope operation.

        Args:
            kind: The kind value used by the operation.
            value: Value to validate, transform, or store.

        Returns:
            None.

        Notes:
            Internal implementation detail for `Scope._register`. It delegates to `_ensure_open`, `own`,
            `register` while keeping intermediate state local to the owning operation.
        """
        self._ensure_open()
        if self._sink is None:
            raise RuntimeError("this scope is not attached to a Cordis manager")
        self.own(self._sink.register(self, kind, value))

    def on(self, handler: object, *, order: int = 0) -> None:
        """Implement the on operation for the scope.

        Args:
            handler: Callable that handles the dispatched value.
            order: Relative handler ordering; lower values run first.

        Returns:
            None.
        """
        self._register("ordered", (order, self._wrap_handler(handler)))

    def parallel(self, handler: object) -> None:
        """Implement the parallel operation for the scope.

        Args:
            handler: Callable that handles the dispatched value.

        Returns:
            None.
        """
        self._register("parallel", self._wrap_handler(handler))

    def middleware(self, handler: object) -> None:
        """Implement the middleware operation for the scope.

        Args:
            handler: Callable that handles the dispatched value.

        Returns:
            None.
        """
        self._register("waterfall", self._wrap_handler(handler))

    def route(self, name: str, predicate: object, handler: object) -> None:
        """Route the scope operation.

        Args:
            name: Stable name used to identify the value.
            predicate: The predicate value used by the operation.
            handler: Callable that handles the dispatched value.

        Returns:
            None.
        """
        if not name:
            raise ValueError("route name must not be empty")
        self._register("route", (name, self._wrap_handler(predicate), self._wrap_handler(handler)))

    def schedule(self, scheduler: object) -> None:
        """Implement the schedule operation for the scope.

        Args:
            scheduler: The scheduler value used by the operation.

        Returns:
            None.
        """
        self._register("scheduler", self._wrap_handler(scheduler))

    def tool(self, tool_id: str, handler: object) -> None:
        """Register exactly one handler for a declared Extension API v2 Tool.

        Args:
            tool_id: Stable identifier for the tool.
            handler: Callable that handles the dispatched value.

        Returns:
            None.
        """

        if not isinstance(tool_id, str) or not tool_id.strip():
            raise ValueError("Tool ID must be non-empty")
        if not callable(handler):
            raise TypeError("Tool handler must be callable")
        self._register("tool", (tool_id, self._wrap_handler(handler)))

    def _wrap_handler(self, handler: object) -> object:
        """Implement the wrap handler operation for the scope.

        Args:
            handler: Callable that handles the dispatched value.

        Returns:
            The `object` result produced by the operation.

        Notes:
            Internal implementation detail for `Scope._wrap_handler`. It delegates to `callable`,
            `validate_runtime_bindings`, `runtime_handler`, `_runtime_context_factory_factory` while keeping
            intermediate state local to the owning operation.
        """
        if self._runtime_context_factory_factory is None or self._runtime_resolver is None or not callable(handler):
            return handler
        validate_runtime_bindings(handler, self._runtime_requirements)
        return runtime_handler(
            handler,
            context_factory=self._runtime_context_factory_factory(self.plugin_id),
            resolver=self._runtime_resolver,
        )

    async def aclose(self) -> None:
        """Close the scope asynchronously.

        Returns:
            None.
        """
        if self._closed:
            return
        self._closed = True
        errors: list[BaseException] = []
        children = tuple(self._children)
        self._children.clear()
        for child in reversed(children):
            try:
                await child.aclose()
            except BaseException as error:
                errors.append(error)
        for disposer in reversed(self._disposers):
            try:
                result = disposer()
                if inspect.isawaitable(result):
                    await result
            except BaseException as error:
                errors.append(error)
        self._instances.clear()
        self._providers.clear()
        self._disposers.clear()
        if self.parent is not None:
            with contextlib.suppress(ValueError):
                self.parent._children.remove(self)
        if errors:
            raise BaseExceptionGroup("Cordis scope cleanup failed", errors)

    def _ensure_open(self) -> None:
        """Implement the ensure open operation for the scope.

        Returns:
            None.

        Notes:
            Internal implementation detail for `Scope._ensure_open`. It performs the local state transition
            directly and is not a stable extension boundary.
        """
        if self._closed:
            raise RuntimeError("Cordis scope is closed")


def _resource_disposer(value: object) -> Disposer | None:
    """Implement the resource disposer operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `Disposer | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_resource_disposer`. It delegates to `getattr`, `callable`,
        `cast` while keeping intermediate state local to the owning operation.
    """
    close = getattr(value, "aclose", None)
    if callable(close):
        return cast(Disposer, close)
    close = getattr(value, "close", None)
    if callable(close):
        return cast(Disposer, close)
    return None
