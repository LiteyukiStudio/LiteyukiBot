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

COMMAND_SERVICE = ServiceKey("liteyukibot.commands", 1)


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

    def snapshot(self) -> tuple[CommandRegistration, ...]: ...

    def visible(self, event: EventEnvelope) -> tuple[CommandRegistration, ...]: ...


@dataclass(frozen=True, slots=True)
class _RegisteredCommand:
    registration: CommandRegistration
    handler: CommandHandler
    tokens: tuple[str, ...]


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
        self._tokens: dict[str, int] = {}
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
        if not owner or owner != owner.strip():
            raise ValueError("command owner must be a non-empty trimmed string")
        pending = tuple(bindings)
        if not pending:
            return ()

        claimed = set(self._tokens)
        prepared: list[tuple[CommandSpec, CommandHandler, tuple[str, ...]]] = []
        for spec, handler in pending:
            if not isinstance(spec, CommandSpec):
                raise TypeError("command binding must contain CommandSpec")
            if not callable(handler):
                raise TypeError(f"handler for command {spec.name} must be callable")
            raw_tokens = (spec.name, *spec.aliases)
            if any(token.startswith(prefix) for token in raw_tokens for prefix in self._prefixes):
                raise ValueError(f"command {spec.name} names and aliases must not include a prefix")
            tokens = tuple(token.casefold() for token in raw_tokens)
            conflict = next((token for token in tokens if token in claimed), None)
            if conflict is not None:
                raise ValueError(f"command name or alias is already registered: {conflict}")
            claimed.update(tokens)
            prepared.append((spec, handler, tokens))

        registrations: list[CommandRegistration] = []
        for spec, handler, tokens in prepared:
            registration = CommandRegistration(self._next_id, owner, spec)
            self._next_id += 1
            self._commands[registration.id] = _RegisteredCommand(registration, handler, tokens)
            for token in tokens:
                self._tokens[token] = registration.id
            registrations.append(registration)
        return tuple(registrations)

    def unregister(self, registration: CommandRegistration) -> bool:
        registered = self._commands.get(registration.id)
        if registered is None or registered.registration != registration:
            return False
        del self._commands[registration.id]
        for token in registered.tokens:
            self._tokens.pop(token, None)
        return True

    def snapshot(self) -> tuple[CommandRegistration, ...]:
        return tuple(
            item.registration
            for item in sorted(
                self._commands.values(),
                key=lambda item: (item.registration.spec.name.casefold(), item.registration.id),
            )
        )

    def visible(self, event: EventEnvelope) -> tuple[CommandRegistration, ...]:
        return tuple(
            registration
            for registration in self.snapshot()
            if self._allows(event, registration.spec)
        )

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
        parts = body.split(maxsplit=1)
        invoked_as = parts[0]
        command_id = self._tokens.get(invoked_as.casefold())
        if command_id is None:
            return None
        raw_arguments = "" if len(parts) == 1 else parts[1]
        return self._commands[command_id], invoked_as, prefix, raw_arguments


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
