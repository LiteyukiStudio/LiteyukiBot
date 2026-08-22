"""Protocol-neutral runtime bridge API declarations and invocation helpers."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from functools import wraps
from importlib import metadata
from typing import Any, Protocol, cast

from pydantic import BaseModel, ConfigDict, field_validator

from .authorization import AuthorizationContext
from .events import EventEnvelope
from .events.models import JsonValue
from .runtime_api_models import BotSnapshot, EventSnapshot, SendResult

RUNTIME_BINDINGS_ATTRIBUTE = "__liteyuki_runtime_bindings__"


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field} must be a non-empty trimmed string")
    return value


class RuntimeRequirement(BaseModel):
    """One extension-level dependency on a runtime API namespace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime: str
    api: str
    version: str = "^1.0"
    operations: tuple[str, ...]
    optional: bool = False
    bridge_id: str | None = None

    @field_validator("runtime", "api", "version")
    @classmethod
    def validate_text(cls, value: str, info: Any) -> str:
        return _identifier(value, info.field_name)

    @field_validator("operations")
    @classmethod
    def validate_operations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(not _identifier(operation, "runtime API operation") for operation in value):
            raise ValueError("runtime API requirements must declare at least one operation")
        if len(value) != len(set(value)):
            raise ValueError("runtime API requirement operations must be unique")
        return value

    @field_validator("bridge_id")
    @classmethod
    def validate_bridge_id(cls, value: str | None) -> str | None:
        return None if value is None else _identifier(value, "runtime API bridge_id")

    @property
    def capability_names(self) -> tuple[str, ...]:
        return tuple(f"runtime.{self.runtime}.{self.api}.{operation}" for operation in self.operations)


@dataclass(frozen=True, slots=True)
class RuntimeBinding:
    """Function-level runtime namespace metadata recorded by :func:`runtime`."""

    runtime: str
    api: str
    version: str
    optional: bool
    alias: str
    bridge_id: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeCallContext:
    """The minimal event and extension identity available to a runtime call."""

    extension_id: str
    event: EventEnvelope
    authorization: AuthorizationContext


class RuntimeApiBackend(Protocol):
    async def invoke(
        self,
        binding: RuntimeBinding,
        operation: str,
        arguments: Mapping[str, JsonValue],
        context: RuntimeCallContext,
    ) -> JsonValue: ...


class RuntimeUnavailable(RuntimeError):
    """Raised when an optional runtime dependency has no compatible provider."""

    def __init__(self, runtime: str, api: str, reason: str = "unavailable") -> None:
        self.runtime = runtime
        self.api = api
        self.reason = reason
        super().__init__(f"runtime API {runtime}.{api} is unavailable: {reason}")


class RuntimeApiError(RuntimeError):
    """Raised for a stable provider-side runtime API failure."""

    def __init__(self, runtime: str, api: str, operation: str, code: str, details: JsonValue = None) -> None:
        self.runtime = runtime
        self.api = api
        self.operation = operation
        self.code = code
        self.details = details
        super().__init__(f"runtime API {runtime}.{api}.{operation} failed: {code}")


class RuntimeNamespaceProxy:
    """Generic JSON-safe namespace proxy used by typed runtime SDK facades."""

    def __init__(
        self,
        binding: RuntimeBinding,
        backend: RuntimeApiBackend | None,
        context: RuntimeCallContext | None,
        *,
        reason: str = "unavailable",
    ) -> None:
        self.binding = binding
        self._backend = backend
        self._context = context
        self._reason = reason

    @property
    def available(self) -> bool:
        return self._backend is not None and self._context is not None

    async def call(self, operation: str, arguments: Mapping[str, JsonValue] | None = None) -> JsonValue:
        if not self.available:
            raise RuntimeUnavailable(self.binding.runtime, self.binding.api, self._reason)
        assert self._backend is not None
        assert self._context is not None
        return await self._backend.invoke(self.binding, operation, arguments or {}, self._context)


RuntimeApiProxy = RuntimeNamespaceProxy


RuntimeResolver = Callable[[RuntimeBinding, RuntimeCallContext], RuntimeNamespaceProxy]
RuntimeContextFactory = Callable[[tuple[Any, ...], Mapping[str, Any]], RuntimeCallContext]
RuntimeProxyFactory = Callable[..., RuntimeNamespaceProxy]


def create_runtime_proxy(
    binding: RuntimeBinding,
    backend: RuntimeApiBackend | None,
    context: RuntimeCallContext | None,
    *,
    reason: str = "unavailable",
) -> RuntimeNamespaceProxy:
    """Load an optional typed SDK facade without making it a kernel dependency."""

    candidates = tuple(
        entry
        for entry in metadata.entry_points(group="liteyukibot.runtime_api_proxies")
        if entry.name == f"{binding.runtime}.{binding.api}"
    )
    if len(candidates) > 1:
        names = ", ".join(entry.name for entry in candidates)
        raise RuntimeError(f"multiple runtime API proxy providers found for {names}")
    if not candidates:
        return RuntimeNamespaceProxy(binding, backend, context, reason=reason)
    factory = candidates[0].load()
    if not callable(factory):
        raise RuntimeError(f"runtime API proxy provider {candidates[0].name!r} is not callable")
    provider = cast(RuntimeProxyFactory, factory)
    return provider(binding=binding, backend=backend, context=context, reason=reason)


def runtime(
    runtime_name: str,
    *,
    api: str,
    version: str = "^1.0",
    optional: bool = False,
    as_: str,
    bridge_id: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declare and later inject one runtime namespace proxy into a callable."""

    binding = RuntimeBinding(
        runtime=_identifier(runtime_name, "runtime name"),
        api=_identifier(api, "runtime API namespace"),
        version=_identifier(version, "runtime API version"),
        optional=optional,
        alias=_identifier(as_, "runtime API alias"),
        bridge_id=None if bridge_id is None else _identifier(bridge_id, "runtime API bridge_id"),
    )

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        if not callable(function):
            raise TypeError("@runtime can decorate only callables")
        try:
            parameter = inspect.signature(function).parameters[binding.alias]
        except (KeyError, TypeError, ValueError) as error:
            raise TypeError(f"@runtime requires a parameter named {binding.alias!r}") from error
        if parameter.kind is not inspect.Parameter.KEYWORD_ONLY:
            raise TypeError(f"@runtime parameter {binding.alias!r} must be keyword-only")
        existing = tuple(getattr(function, RUNTIME_BINDINGS_ATTRIBUTE, ()))
        if any(item.alias == binding.alias for item in existing):
            raise TypeError(f"@runtime alias {binding.alias!r} is duplicated")
        setattr(function, RUNTIME_BINDINGS_ATTRIBUTE, (*existing, binding))
        return function

    return decorate


def runtime_bindings(function: Callable[..., Any]) -> tuple[RuntimeBinding, ...]:
    """Return static runtime metadata without importing a framework SDK."""

    return tuple(getattr(function, RUNTIME_BINDINGS_ATTRIBUTE, ()))


def validate_runtime_bindings(
    function: Callable[..., Any], requirements: tuple[RuntimeRequirement, ...]
) -> None:
    """Reject undeclared or ambiguous runtime namespaces at host registration time."""

    for binding in runtime_bindings(function):
        candidates = [
            requirement
            for requirement in requirements
            if requirement.runtime == binding.runtime
            and requirement.api == binding.api
            and requirement.version == binding.version
            and requirement.optional == binding.optional
            and (requirement.bridge_id is None or binding.bridge_id in (None, requirement.bridge_id))
        ]
        if binding.bridge_id is not None:
            exact = [item for item in candidates if item.bridge_id == binding.bridge_id]
            candidates = exact or [item for item in candidates if item.bridge_id is None]
        if len(candidates) != 1:
            raise TypeError(
                f"runtime binding {binding.runtime}.{binding.api} is not uniquely declared by the extension manifest"
            )


async def invoke_with_runtime(
    function: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
    *,
    context_factory: RuntimeContextFactory,
    resolver: RuntimeResolver,
) -> Any:
    """Invoke one decorated callable with host-owned namespace proxies."""

    bound_kwargs = dict(kwargs)
    context = context_factory(args, bound_kwargs)
    for binding in runtime_bindings(function):
        bound_kwargs[binding.alias] = resolver(binding, context)
    result = function(*args, **bound_kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def runtime_handler(
    function: Callable[..., Any],
    *,
    context_factory: RuntimeContextFactory,
    resolver: RuntimeResolver,
) -> Callable[..., Awaitable[Any]]:
    """Return an async lifecycle wrapper for an existing host callback."""

    if not runtime_bindings(function):
        async def plain(*args: Any, **kwargs: Any) -> Any:
            result = function(*args, **kwargs)
            return await result if inspect.isawaitable(result) else result

        return plain

    @wraps(function)
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        return await invoke_with_runtime(
            function,
            args,
            kwargs,
            context_factory=context_factory,
            resolver=resolver,
        )

    return wrapped


__all__ = [
    "BotSnapshot",
    "EventSnapshot",
    "RuntimeApiBackend",
    "RuntimeApiError",
    "RuntimeApiProxy",
    "RuntimeBinding",
    "RuntimeCallContext",
    "RuntimeNamespaceProxy",
    "RuntimeProxyFactory",
    "RuntimeRequirement",
    "RuntimeUnavailable",
    "SendResult",
    "invoke_with_runtime",
    "create_runtime_proxy",
    "runtime",
    "runtime_bindings",
    "runtime_handler",
    "validate_runtime_bindings",
]
