"""Small scoped dependency container used by the in-process Cordis host."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import Awaitable, Callable, Hashable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import uuid4

type Provider = Callable[[Scope], Any] | Callable[[], Any]
type Disposer = Callable[[], Awaitable[None]]

_PROVIDER_STACK: ContextVar[tuple[Hashable, ...]] = ContextVar("cordis_provider_stack", default=())


def _is_async_callable(value: object) -> bool:
    """Return whether a callback is an async function or async callable object."""

    if inspect.iscoroutinefunction(value):
        return True
    return callable(value) and inspect.iscoroutinefunction(cast(Any, value).__call__)


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
        self._resolutions: dict[Hashable, asyncio.Task[object]] = {}
        self._disposers: list[Disposer] = []
        self._children: list[Scope] = []
        self._closed = False
        self._cleanup_complete = False
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
        if not _is_async_callable(disposer):
            raise TypeError("Cordis disposers must be async callables")
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
        if self._cleanup_complete:
            return
        self._closed = True
        errors: list[BaseException] = []
        current_task = asyncio.current_task()
        resolutions = tuple(
            task for task in self._resolutions.values() if task is not current_task and not task.done()
        )
        for task in resolutions:
            task.cancel()
        if resolutions:
            await asyncio.gather(*resolutions, return_exceptions=True)
        self._resolutions.clear()
        children = tuple(self._children)
        for child in reversed(children):
            try:
                await child.aclose()
            except BaseException as error:
                errors.append(error)
        disposer_failed = False
        for disposer in reversed(tuple(self._disposers)):
            if disposer not in self._disposers:
                continue
            try:
                result = disposer()
                if inspect.isawaitable(result):
                    await result
            except BaseException as error:
                disposer_failed = True
                errors.append(error)
            else:
                with contextlib.suppress(ValueError):
                    self._disposers.remove(disposer)
        if not disposer_failed:
            self._instances.clear()
            self._providers.clear()
        if errors:
            raise BaseExceptionGroup("Cordis scope cleanup failed", errors)
        self._cleanup_complete = True
        if self.parent is not None:
            with contextlib.suppress(ValueError):
                self.parent._children.remove(self)

    async def _resolve(self, key: Hashable) -> object:
        if key in self._instances:
            return self._instances[key]
        stack = _PROVIDER_STACK.get()
        if key in stack:
            chain = " -> ".join(repr(item) for item in (*stack, key))
            raise ProviderCycleError(f"Cordis provider dependency cycle: {chain}")
        self._ensure_open()
        task = self._resolutions.get(key)
        if task is None:
            token = _PROVIDER_STACK.set((*stack, key))
            try:
                task = asyncio.create_task(self._resolve_provider(key), name=f"cordis-provider-{key!r}")
            finally:
                _PROVIDER_STACK.reset(token)
            self._resolutions[key] = task
            task.add_done_callback(lambda completed: self._resolution_done(key, completed))
        return await asyncio.shield(task)

    async def _resolve_provider(self, key: Hashable) -> object:
        provider = self._providers[key]
        try:
            parameters = inspect.signature(provider).parameters
        except (TypeError, ValueError):
            value = provider()  # type: ignore[call-arg]
        else:
            value = provider(self) if parameters else provider()  # type: ignore[call-arg]
        if inspect.isawaitable(value):
            value = await value
        disposer = _resource_disposer(value)
        self._instances[key] = value
        if disposer is not None:
            self._disposers.append(disposer)
        return value

    def _resolution_done(self, key: Hashable, task: asyncio.Future[object]) -> None:
        if self._resolutions.get(key) is task:
            del self._resolutions[key]
        with contextlib.suppress(asyncio.CancelledError):
            task.exception()

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
        if not _is_async_callable(close):
            raise TypeError("Cordis resource aclose must be an async callable")
        return cast(Disposer, close)
    close = getattr(value, "close", None)
    if callable(close):
        if not _is_async_callable(close):
            raise TypeError("Cordis resource close must be an async callable")
        return cast(Disposer, close)
    return None


__all__ = ["Disposer", "ProviderCycleError", "Scope", "UnavailableProviderError"]
