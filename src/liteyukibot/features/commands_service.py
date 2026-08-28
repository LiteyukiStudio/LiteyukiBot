"""Command registry, parser, and EventBus handler."""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol, cast

from liteyukibot_kernel.events import EventEnvelope, HandlerFailure, HandlerResult
from liteyukibot_kernel.services import ServiceKey

from .commands_models import (
    CommandBinding,
    CommandHandler,
    CommandInvocation,
    CommandRegistration,
    CommandSpec,
)
from .commands_parsing import CommandParseError
from .common import run_blocking
from .permissions import PermissionService

COMMAND_SERVICE = ServiceKey("liteyukibot.commands", 2)


def _is_async_callable(value: object) -> bool:
    """Return whether a callback is an async function or async callable object."""

    if inspect.iscoroutinefunction(value):
        return True
    return callable(value) and inspect.iscoroutinefunction(cast(Any, value).__call__)


class _Logger(Protocol):
    """Define the structural interface required from a logger."""
    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Implement the warning operation for the logger.

        Args:
            message: Message content associated with the operation.
            *args: The args value used by the operation.
            **kwargs: The kwargs value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_Logger.warning`. It performs the local state transition
            directly and is not a stable extension boundary.
        """
        ...

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Implement the error operation for the logger.

        Args:
            message: Message content associated with the operation.
            *args: The args value used by the operation.
            **kwargs: The kwargs value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_Logger.error`. It performs the local state transition
            directly and is not a stable extension boundary.
        """
        ...

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Implement the exception operation for the logger.

        Args:
            message: Message content associated with the operation.
            *args: The args value used by the operation.
            **kwargs: The kwargs value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_Logger.exception`. It performs the local state transition
            directly and is not a stable extension boundary.
        """
        ...


class CommandService(Protocol):
    """Define the structural interface required from a command service."""
    def register(
        self,
        spec: CommandSpec,
        handler: CommandHandler,
        *,
        owner: str,
    ) -> CommandRegistration:
        """Register the command service operation.

        Args:
            spec: The spec value used by the operation.
            handler: Callable that handles the dispatched value.
            owner: Stable owner identity for the registration.

        Returns:
            The `CommandRegistration` result produced by the operation.
        """
        ...

    def register_many(
        self,
        bindings: Sequence[CommandBinding],
        *,
        owner: str,
    ) -> tuple[CommandRegistration, ...]:
        """Register many.

        Args:
            bindings: The bindings value used by the operation.
            owner: Stable owner identity for the registration.

        Returns:
            The `tuple[CommandRegistration, ...]` result produced by the operation.
        """
        ...

    def unregister(self, registration: CommandRegistration) -> bool:
        """Unregister the command service operation.

        Args:
            registration: The registration value used by the operation.

        Returns:
            Whether the requested condition is satisfied.
        """
        ...

    def unregister_owner(self, owner: str) -> int:
        """Unregister owner.

        Args:
            owner: Stable owner identity for the registration.

        Returns:
            The `int` result produced by the operation.
        """
        ...

    def snapshot(self) -> tuple[CommandRegistration, ...]:
        """Return an immutable snapshot of the command service state.

        Returns:
            The requested `tuple[CommandRegistration, ...]` value.
        """
        ...

    def visible(self, event: EventEnvelope) -> tuple[CommandRegistration, ...]:
        """Implement the visible operation for the command service.

        Args:
            event: Event associated with the operation.

        Returns:
            The `tuple[CommandRegistration, ...]` result produced by the operation.
        """
        ...

    def resolve(self, event: EventEnvelope, path: Sequence[str]) -> CommandRegistration | None:
        """Resolve the command service operation.

        Args:
            event: Event associated with the operation.
            path: Filesystem or logical resource path.

        Returns:
            The requested `CommandRegistration | None` value.
        """
        ...


@dataclass(frozen=True, slots=True)
class _RegisteredCommand:
    """Represent the registered command contract."""
    registration: CommandRegistration
    handler: CommandHandler
    paths: tuple[tuple[str, ...], ...]


class _CommandService:
    """Represent the command service contract."""
    def __init__(
        self,
        prefixes: tuple[str, ...],
        permissions: PermissionService,
        logger: _Logger,
    ) -> None:
        """Initialize the command service.

        Args:
            prefixes: The prefixes value used by the operation.
            permissions: The permissions value used by the operation.
            logger: Structured logger used for diagnostics.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_CommandService.__init__`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        self._prefixes = prefixes
        self._permissions = permissions
        self._logger = logger
        self._commands: dict[int, _RegisteredCommand] = {}
        self._paths: dict[tuple[str, ...], int] = {}
        self._max_path_length = 0
        self._next_id = 0

    def register(
        self,
        spec: CommandSpec,
        handler: CommandHandler,
        *,
        owner: str,
    ) -> CommandRegistration:
        """Register the command service operation.

        Args:
            spec: The spec value used by the operation.
            handler: Callable that handles the dispatched value.
            owner: Stable owner identity for the registration.

        Returns:
            The `CommandRegistration` result produced by the operation.

        Notes:
            Internal implementation detail for `_CommandService.register`. It delegates to `register_many`
            while keeping intermediate state local to the owning operation.
        """
        return self.register_many(((spec, handler),), owner=owner)[0]

    def register_many(
        self,
        bindings: Sequence[CommandBinding],
        *,
        owner: str,
    ) -> tuple[CommandRegistration, ...]:
        """Register many.

        Args:
            bindings: The bindings value used by the operation.
            owner: Stable owner identity for the registration.

        Returns:
            The `tuple[CommandRegistration, ...]` result produced by the operation.

        Notes:
            Internal implementation detail for `_CommandService.register_many`. It delegates to
            `_validate_owner`, `callable`, `any`, `startswith` while keeping intermediate state local to the
            owning operation.
        """
        _validate_owner(owner)
        pending = tuple(bindings)
        if not pending:
            return ()

        claimed = set(self._paths)
        prepared: list[tuple[CommandSpec, CommandHandler, tuple[tuple[str, ...], ...]]] = []
        for spec, handler in pending:
            if not isinstance(spec, CommandSpec):
                raise TypeError("command binding must contain CommandSpec")
            if not callable(handler):
                raise TypeError(f"handler for command {spec.name} must be callable")
            if not _is_async_callable(handler):
                raise TypeError(f"handler for command {spec.name} must be an async callable")
            raw_tokens = (*spec.path, spec.name, *spec.aliases)
            if any(token.startswith(prefix) for token in raw_tokens for prefix in self._prefixes):
                raise ValueError(f"command {spec.name} names and aliases must not include a prefix")
            paths = (
                tuple(token.casefold() for token in spec.command_path),
                *(tuple(token.casefold() for token in (*spec.path, alias)) for alias in spec.aliases),
            )
            conflict = next((path for path in paths if path in claimed), None)
            if conflict is not None:
                raise ValueError(f"command name or alias is already registered: {' '.join(conflict)}")
            claimed.update(paths)
            prepared.append((spec, handler, paths))

        registrations: list[CommandRegistration] = []
        for spec, handler, paths in prepared:
            registration = CommandRegistration(self._next_id, owner, spec)
            self._next_id += 1
            self._commands[registration.id] = _RegisteredCommand(registration, handler, paths)
            for path in paths:
                self._paths[path] = registration.id
                self._max_path_length = max(self._max_path_length, len(path))
            registrations.append(registration)
        return tuple(registrations)

    def unregister(self, registration: CommandRegistration) -> bool:
        """Unregister the command service operation.

        Args:
            registration: The registration value used by the operation.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `_CommandService.unregister`. It delegates to `get`,
            `_remove`, `_refresh_max_path_length` while keeping intermediate state local to the owning
            operation.
        """
        registered = self._commands.get(registration.id)
        if registered is None or registered.registration != registration:
            return False
        self._remove(registered)
        self._refresh_max_path_length()
        return True

    def unregister_owner(self, owner: str) -> int:
        """Unregister owner.

        Args:
            owner: Stable owner identity for the registration.

        Returns:
            The `int` result produced by the operation.

        Notes:
            Internal implementation detail for `_CommandService.unregister_owner`. It delegates to
            `_validate_owner`, `values`, `_remove`, `_refresh_max_path_length` while keeping intermediate
            state local to the owning operation.
        """
        _validate_owner(owner)
        registrations = tuple(
            registered
            for registered in self._commands.values()
            if registered.registration.owner == owner
        )
        for registered in registrations:
            self._remove(registered)
        if registrations:
            self._refresh_max_path_length()
        return len(registrations)

    def snapshot(self) -> tuple[CommandRegistration, ...]:
        """Return an immutable snapshot of the command service state.

        Returns:
            The requested `tuple[CommandRegistration, ...]` value.

        Notes:
            Internal implementation detail for `_CommandService.snapshot`. It delegates to `sorted`,
            `values`, `casefold` while keeping intermediate state local to the owning operation.
        """
        return tuple(
            item.registration
            for item in sorted(
                self._commands.values(),
                key=lambda item: (
                    tuple(segment.casefold() for segment in item.registration.spec.command_path),
                    item.registration.id,
                ),
            )
        )

    def visible(self, event: EventEnvelope) -> tuple[CommandRegistration, ...]:
        """Implement the visible operation for the command service.

        Args:
            event: Event associated with the operation.

        Returns:
            The `tuple[CommandRegistration, ...]` result produced by the operation.

        Notes:
            Internal implementation detail for `_CommandService.visible`. It delegates to `snapshot`,
            `_allows` while keeping intermediate state local to the owning operation.
        """
        return tuple(
            registration
            for registration in self.snapshot()
            if self._allows(event, registration.spec)
        )

    def resolve(self, event: EventEnvelope, path: Sequence[str]) -> CommandRegistration | None:
        """Resolve the command service operation.

        Args:
            event: Event associated with the operation.
            path: Filesystem or logical resource path.

        Returns:
            The requested `CommandRegistration | None` value.

        Notes:
            Internal implementation detail for `_CommandService.resolve`. It delegates to `casefold`, `get`,
            `_allows` while keeping intermediate state local to the owning operation.
        """
        tokens = tuple(item.casefold() for item in path)
        registration_id = self._paths.get(tokens)
        if registration_id is None:
            return None
        registration = self._commands[registration_id].registration
        return registration if self._allows(event, registration.spec) else None

    async def dispatch(self, event: EventEnvelope) -> HandlerResult | None:
        """Dispatch the command service operation.

        Args:
            event: Event associated with the operation.

        Returns:
            The `HandlerResult | None` result produced by the operation.

        Notes:
            Internal implementation detail for `_CommandService.dispatch`. It delegates to `_parse`,
            `_allows`, `handler`, `isawaitable` while keeping intermediate state local to the owning
            operation.
        """
        parsed = self._parse(event)
        if parsed is None:
            return None
        registered, invoked_as, prefix, raw_arguments = parsed
        spec = registered.registration.spec
        if not self._allows(event, spec):
            return HandlerResult(stop_propagation=True)

        invocation = CommandInvocation(
            event=event,
            command=spec.name,
            invoked_as=invoked_as,
            prefix=prefix,
            raw_arguments=raw_arguments,
            schema=spec.schema,
            command_path=spec.command_path,
        )
        try:
            try:
                parsed_invocation = await run_blocking(invocation.parse)
            except CommandParseError as error:
                invocation = replace(invocation, _parse_error=error)
            else:
                invocation = replace(invocation, _parsed=parsed_invocation)
            result = await registered.handler(invocation)
        except Exception as error:
            error_type = type(error).__name__
            self._logger.error(
                "command {} handler owned by {} failed: {}",
                spec.name,
                registered.registration.owner,
                error_type,
                event_id=event.id,
            )
            return HandlerResult(
                failures=(
                    HandlerFailure(
                        handler=f"command:{spec.name}",
                        kind="error",
                        message=f"{error_type}: command handler failed",
                    ),
                ),
                stop_propagation=True,
            )
        if result is None:
            return HandlerResult(stop_propagation=True)
        if not isinstance(result, HandlerResult):
            self._logger.error(
                "command {} handler owned by {} returned {} instead of HandlerResult",
                spec.name,
                registered.registration.owner,
                type(result).__name__,
                event_id=event.id,
            )
            return HandlerResult(
                failures=(
                    HandlerFailure(
                        handler=f"command:{spec.name}",
                        kind="invalid_result",
                        message=f"expected HandlerResult or None, got {type(result).__name__}",
                    ),
                ),
                stop_propagation=True,
            )
        return HandlerResult(
            actions=result.actions,
            action_results=result.action_results,
            failures=result.failures,
            stop_propagation=True,
        )

    def _allows(self, event: EventEnvelope, spec: CommandSpec) -> bool:
        """Determine whether the command service operation is allowed.

        Args:
            event: Event associated with the operation.
            spec: The spec value used by the operation.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `_CommandService._allows`. It delegates to `allows`,
            `exception` while keeping intermediate state local to the owning operation.
        """
        try:
            return self._permissions.allows(event, spec.permission)
        except Exception as error:
            self._logger.error(
                "permission check for command {} failed: {}",
                spec.name,
                type(error).__name__,
                event_id=event.id,
            )
            return False

    def _remove(self, registered: _RegisteredCommand) -> None:
        """Remove the command service operation.

        Args:
            registered: The registered value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_CommandService._remove`. It delegates to `pop` while
            keeping intermediate state local to the owning operation.
        """
        del self._commands[registered.registration.id]
        for path in registered.paths:
            self._paths.pop(path, None)

    def _refresh_max_path_length(self) -> None:
        """Implement the refresh max path length operation for the command service.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_CommandService._refresh_max_path_length`. It delegates to
            `max` while keeping intermediate state local to the owning operation.
        """
        self._max_path_length = max((len(path) for path in self._paths), default=0)

    def _parse(self, event: EventEnvelope) -> tuple[_RegisteredCommand, str, str, str] | None:
        """Parse the command service operation.

        Args:
            event: Event associated with the operation.

        Returns:
            The `tuple[_RegisteredCommand, str, str, str] | None` result produced by the operation.

        Notes:
            Internal implementation detail for `_CommandService._parse`. It delegates to `lstrip`, `next`,
            `startswith`, `isspace` while keeping intermediate state local to the owning operation.
        """
        if event.message is None:
            return None
        text = event.message.plain_text.lstrip()
        prefix = next((item for item in self._prefixes if text.startswith(item)), None)
        if prefix is None:
            return None
        body = text[len(prefix) :]
        if not body or body[0].isspace():
            return None
        tokens = _command_tokens(body)
        for length in range(min(self._max_path_length, len(tokens)), 0, -1):
            candidate = tuple(token.casefold() for token, _, _ in tokens[:length])
            command_id = self._paths.get(candidate)
            if command_id is None:
                continue
            _, _, end = tokens[length - 1]
            return self._commands[command_id], body[:end], prefix, body[end:].lstrip()
        return None


def _command_tokens(value: str) -> tuple[tuple[str, int, int], ...]:
    """Implement the command tokens operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `tuple[tuple[str, int, int], ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_command_tokens`. It delegates to `isspace`, `append` while
        keeping intermediate state local to the owning operation.
    """
    tokens: list[tuple[str, int, int]] = []
    start = 0
    while start < len(value):
        while start < len(value) and value[start].isspace():
            start += 1
        if start == len(value):
            break
        end = start
        while end < len(value) and not value[end].isspace():
            end += 1
        tokens.append((value[start:end], start, end))
        start = end
    return tuple(tokens)


def _validate_owner(owner: str) -> None:
    """Validate owner.

    Args:
        owner: Stable owner identity for the registration.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_validate_owner`. It delegates to `strip` while keeping
        intermediate state local to the owning operation.
    """
    if not owner or owner != owner.strip():
        raise ValueError("command owner must be a non-empty trimmed string")


def create_command_service(
    config: Mapping[str, Any],
    permissions: PermissionService,
    logger: _Logger,
) -> _CommandService:
    """Create command service.

    Args:
        config: Validated configuration used by the operation.
        permissions: The permissions value used by the operation.
        logger: Structured logger used for diagnostics.

    Returns:
        The `_CommandService` result produced by the operation.
    """
    unknown = set(config) - {"prefixes"}
    if unknown:
        raise ValueError(f"unknown command config keys: {', '.join(sorted(unknown))}")
    raw_prefixes = config.get("prefixes", ("/",))
    if not isinstance(raw_prefixes, Sequence) or isinstance(raw_prefixes, (str, bytes)):
        raise TypeError("command prefixes must be a sequence of strings")
    prefixes: list[str] = []
    for index, prefix in enumerate(raw_prefixes):
        if not isinstance(prefix, str):
            raise TypeError(f"command prefixes[{index}] must be a string")
        if not prefix or any(character.isspace() for character in prefix):
            raise ValueError(f"command prefixes[{index}] must be non-empty and contain no whitespace")
        if prefix in prefixes:
            raise ValueError(f"command prefixes[{index}] duplicates an earlier prefix")
        prefixes.append(prefix)
    if not prefixes:
        raise ValueError("command prefixes must not be empty")
    return _CommandService(tuple(sorted(prefixes, key=lambda item: (-len(item), item))), permissions, logger)


__all__ = ["COMMAND_SERVICE", "CommandService"]
