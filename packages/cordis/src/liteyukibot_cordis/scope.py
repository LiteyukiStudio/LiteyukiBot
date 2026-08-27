"""Small scoped dependency container used by the in-process Cordis host."""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Awaitable, Callable, Hashable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import uuid4

type Provider = Callable[[Scope], Any] | Callable[[], Any]
type Disposer = Callable[[], Awaitable[None] | None]


class RegistrationSink(Protocol):
    def register(self, scope: Scope, order: int, handler: object) -> Disposer:
        """Register an ordered handler and return its cleanup callback."""
        ...


@dataclass(frozen=True, slots=True)
class UnavailableProviderError(LookupError):
    """Raised when no scope in the ancestor chain provides a key."""

    key: Hashable

    def __str__(self) -> str:
        return f"Cordis provider {self.key!r} is unavailable"


class ProviderCycleError(RuntimeError):
    """Raised when lazy provider resolution detects a cycle."""


class Scope:
    """A tree-owned resource scope with lazy providers and deterministic cleanup."""

    def __init__(
        self,
        *,
        plugin_id: str,
        config: Mapping[str, object] | None = None,
        parent: Scope | None = None,
        sink: RegistrationSink | None = None,
    ) -> None:
        self.id = str(uuid4())
        self.plugin_id = plugin_id
        self.config: Mapping[str, object] = config if config is not None else parent.config if parent else {}
        self.parent = parent
        self._sink: RegistrationSink | None = sink if sink is not None else parent._sink if parent else None
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
        """Register one lazy provider in this scope."""
        self._ensure_open()
        if key in self._providers:
            raise ValueError(f"Cordis provider {key!r} is already registered in this scope")
        if not callable(provider):
            raise TypeError("Cordis provider must be callable")
        self._providers[key] = provider

    async def use(self, key: Hashable) -> object:
        """Resolve a provider from this scope or one of its ancestors."""
        owner = self._find_provider_owner(key)
        if owner is None:
            raise UnavailableProviderError(key)
        return await owner._resolve(key)

    def own(self, disposer: Disposer) -> None:
        """Own a cleanup callback; callbacks run in reverse registration order."""
        self._ensure_open()
        if not callable(disposer):
            raise TypeError("Cordis disposer must be callable")
        self._disposers.append(disposer)

    def on(self, handler: object, *, order: int = 0) -> None:
        """Register one ordered event handler for this scope."""
        self._ensure_open()
        if not callable(handler):
            raise TypeError("Cordis event handler must be callable")
        if self._sink is None:
            raise RuntimeError("this scope is not attached to a Cordis manager")
        self.own(self._sink.register(self, order, handler))

    async def aclose(self) -> None:
        """Close descendants and owned resources deterministically."""
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
            try:
                parameters = inspect.signature(provider).parameters
            except (TypeError, ValueError):
                value = provider()  # type: ignore[call-arg]
            else:
                value = provider(self) if parameters else provider()  # type: ignore[call-arg]
            if inspect.isawaitable(value):
                value = await value
            self._instances[key] = value
            disposer = _resource_disposer(value)
            if disposer is not None:
                self._disposers.append(disposer)
            return value
        finally:
            self._resolving.pop()

    def _find_provider_owner(self, key: Hashable) -> Scope | None:
        scope: Scope | None = self
        while scope is not None:
            if key in scope._providers:
                return scope
            scope = scope.parent
        return None

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


__all__ = ["Disposer", "ProviderCycleError", "Scope", "UnavailableProviderError"]
