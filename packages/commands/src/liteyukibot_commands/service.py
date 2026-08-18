"""Command registry, parser, and EventBus handler."""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from liteyukibot_permissions import PermissionService

from liteyukibot.events import EventEnvelope, HandlerResult
from liteyukibot.services import ServiceKey

from .models import (
    CommandBinding,
    CommandHandler,
    CommandInvocation,
    CommandRegistration,
    CommandSpec,
)

COMMAND_SERVICE = ServiceKey("liteyukibot.commands", 2)


class _Logger(Protocol):
    def warning(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def error(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None: ...


class CommandService(Protocol):
    def register(
        self,
        spec: CommandSpec,
        handler: CommandHandler,
        *,
        owner: str,
    ) -> CommandRegistration: ...

    def register_many(
        self,
        bindings: Sequence[CommandBinding],
        *,
        owner: str,
    ) -> tuple[CommandRegistration, ...]: ...

    def unregister(self, registration: CommandRegistration) -> bool: ...

    def unregister_owner(self, owner: str) -> int: ...

    def snapshot(self) -> tuple[CommandRegistration, ...]: ...

    def visible(self, event: EventEnvelope) -> tuple[CommandRegistration, ...]: ...

    def resolve(self, event: EventEnvelope, path: Sequence[str]) -> CommandRegistration | None: ...


@dataclass(frozen=True, slots=True)
class _RegisteredCommand:
    registration: CommandRegistration
    handler: CommandHandler
    paths: tuple[tuple[str, ...], ...]


class _CommandService:
    def __init__(
        self,
        prefixes: tuple[str, ...],
        permissions: PermissionService,
        logger: _Logger,
    ) -> None:
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
        return self.register_many(((spec, handler),), owner=owner)[0]

    def register_many(
        self,
        bindings: Sequence[CommandBinding],
        *,
        owner: str,
    ) -> tuple[CommandRegistration, ...]:
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
        registered = self._commands.get(registration.id)
        if registered is None or registered.registration != registration:
            return False
        self._remove(registered)
        self._refresh_max_path_length()
        return True

    def unregister_owner(self, owner: str) -> int:
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
        return tuple(
            registration
            for registration in self.snapshot()
            if self._allows(event, registration.spec)
        )

    def resolve(self, event: EventEnvelope, path: Sequence[str]) -> CommandRegistration | None:
        tokens = tuple(item.casefold() for item in path)
        registration_id = self._paths.get(tokens)
        if registration_id is None:
            return None
        registration = self._commands[registration_id].registration
        return registration if self._allows(event, registration.spec) else None

    async def dispatch(self, event: EventEnvelope) -> HandlerResult | None:
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
            result: Any = registered.handler(invocation)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            self._logger.exception(
                "command {} handler owned by {} failed",
                spec.name,
                registered.registration.owner,
                event_id=event.id,
            )
            return HandlerResult(stop_propagation=True)
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
            return HandlerResult(stop_propagation=True)
        return HandlerResult(actions=result.actions, stop_propagation=True)

    def _allows(self, event: EventEnvelope, spec: CommandSpec) -> bool:
        try:
            return self._permissions.allows(event, spec.permission)
        except Exception:
            self._logger.exception(
                "permission check for command {} failed",
                spec.name,
                event_id=event.id,
            )
            return False

    def _remove(self, registered: _RegisteredCommand) -> None:
        del self._commands[registered.registration.id]
        for path in registered.paths:
            self._paths.pop(path, None)

    def _refresh_max_path_length(self) -> None:
        self._max_path_length = max((len(path) for path in self._paths), default=0)

    def _parse(self, event: EventEnvelope) -> tuple[_RegisteredCommand, str, str, str] | None:
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
    if not owner or owner != owner.strip():
        raise ValueError("command owner must be a non-empty trimmed string")


def create_command_service(
    config: Mapping[str, Any],
    permissions: PermissionService,
    logger: _Logger,
) -> _CommandService:
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
