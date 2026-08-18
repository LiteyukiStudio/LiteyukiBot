"""Scoped dynamic providers and owned lifecycle cleanup."""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Awaitable, Callable, Hashable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import uuid4

from .audit import CordisAuditService

type Provider = Callable[[Scope], Any] | Callable[[], Any]
type Disposer = Callable[[], Awaitable[None] | None]


class RegistrationSink(Protocol):
    def register(self, scope: Scope, kind: str, value: object) -> Disposer: ...


@dataclass(frozen=True, slots=True)
class UnavailableProviderError(LookupError):
    key: Hashable

    def __str__(self) -> str:
        return f"Cordis provider {self.key!r} is unavailable"


class ProviderCycleError(RuntimeError):
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
    ) -> None:
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
        return self._closed

    def child(self, *, plugin_id: str | None = None, config: Mapping[str, object] | None = None) -> Scope:
        self._ensure_open()
        return Scope(plugin_id=plugin_id or self.plugin_id, config=config, parent=self)

    def provide(self, key: Hashable, provider: Provider) -> None:
        self._ensure_open()
        if key in self._providers:
            raise ValueError(f"Cordis provider {key!r} is already registered in this scope")
        self._providers[key] = provider

    def own(self, disposer: Disposer) -> None:
        self._ensure_open()
        self._disposers.append(disposer)

    async def use(self, key: Hashable) -> object:
        owner = self._find_provider_owner(key)
        if owner is None:
            raise UnavailableProviderError(key)
        return await owner._resolve(key)

    async def _resolve(self, key: Hashable) -> object:
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
        try:
            parameters = inspect.signature(provider).parameters
        except TypeError, ValueError:
            return provider()  # type: ignore[call-arg]
        return provider(self) if parameters else provider()  # type: ignore[call-arg]

    def _find_provider_owner(self, key: Hashable) -> Scope | None:
        scope: Scope | None = self
        while scope is not None:
            if key in scope._providers:
                return scope
            scope = scope.parent
        return None

    def _register(self, kind: str, value: object) -> None:
        self._ensure_open()
        if self._sink is None:
            raise RuntimeError("this scope is not attached to a Cordis manager")
        self.own(self._sink.register(self, kind, value))

    def on(self, handler: object, *, order: int = 0) -> None:
        self._register("ordered", (order, handler))

    def parallel(self, handler: object) -> None:
        self._register("parallel", handler)

    def middleware(self, handler: object) -> None:
        self._register("waterfall", handler)

    def route(self, name: str, predicate: object, handler: object) -> None:
        if not name:
            raise ValueError("route name must not be empty")
        self._register("route", (name, predicate, handler))

    def schedule(self, scheduler: object) -> None:
        self._register("scheduler", scheduler)

    def tool(self, tool_id: str, handler: object) -> None:
        """Register exactly one handler for a declared Extension API v2 Tool."""

        if not isinstance(tool_id, str) or not tool_id.strip():
            raise ValueError("Tool ID must be non-empty")
        if not callable(handler):
            raise TypeError("Tool handler must be callable")
        self._register("tool", (tool_id, handler))

    async def aclose(self) -> None:
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
        if self._closed:
            raise RuntimeError("Cordis scope is closed")


def _resource_disposer(value: object) -> Disposer | None:
    close = getattr(value, "aclose", None)
    if callable(close):
        return cast(Disposer, close)
    close = getattr(value, "close", None)
    if callable(close):
        return cast(Disposer, close)
    return None
