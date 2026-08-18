"""Resource registry and principal-aware operation dispatch."""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from liteyukibot_commands import (
    ArgumentSpec,
    CommandBinding,
    CommandInvocation,
    CommandParseError,
    CommandRegistration,
    CommandSchema,
    CommandService,
    CommandSpec,
    OptionSpec,
)
from liteyukibot_permissions import PermissionService, Principal

from liteyukibot.authorization import AuthorizationContext
from liteyukibot.events import EventEnvelope, HandlerResult
from liteyukibot.i18n import Translator
from liteyukibot.services import ServiceKey

from .models import ResourceField, ResourceOperation, ResourceProvider, ResourceRegistration, ResourceSpec

RESOURCE_SERVICE = ServiceKey("liteyukibot.resources", 2)


class ResourceError(ValueError):
    """Raised when a resource operation cannot be performed."""


class ResourceService(Protocol):
    def register(
        self,
        spec: ResourceSpec,
        provider: ResourceProvider,
        *,
        owner: str,
    ) -> ResourceRegistration: ...

    def register_many(
        self,
        bindings: Sequence[tuple[ResourceSpec, ResourceProvider]],
        *,
        owner: str,
    ) -> tuple[ResourceRegistration, ...]: ...

    def unregister(self, registration: ResourceRegistration) -> bool: ...

    def snapshot(self) -> tuple[ResourceRegistration, ...]: ...

    def resolve(self, path: Sequence[str]) -> ResourceRegistration | None: ...

    async def inspect(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        *,
        actor_id: str | None = None,
    ) -> Mapping[str, object]: ...

    async def set(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        field: str,
        value: str,
        *,
        actor_id: str | None = None,
    ) -> None: ...

    async def delete(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        field: str,
        *,
        actor_id: str | None = None,
    ) -> None: ...

    async def inspect_context(
        self,
        context: AuthorizationContext,
        path: Sequence[str],
    ) -> Mapping[str, object]: ...

    async def set_context(
        self,
        context: AuthorizationContext,
        path: Sequence[str],
        field: str,
        value: str,
    ) -> None: ...

    async def delete_context(
        self,
        context: AuthorizationContext,
        path: Sequence[str],
        field: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class _RegisteredResource:
    registration: ResourceRegistration
    provider: ResourceProvider
    commands: tuple[CommandRegistration, ...]


class _ResourceService:
    def __init__(self, permissions: PermissionService, commands: CommandService, translator: Translator) -> None:
        self._permissions = permissions
        self._commands = commands
        self._translator = translator
        self._resources: dict[int, _RegisteredResource] = {}
        self._paths: dict[tuple[str, ...], int] = {}
        self._next_id = 0

    def register(
        self,
        spec: ResourceSpec,
        provider: ResourceProvider,
        *,
        owner: str,
    ) -> ResourceRegistration:
        return self.register_many(((spec, provider),), owner=owner)[0]

    def register_many(
        self,
        bindings: Sequence[tuple[ResourceSpec, ResourceProvider]],
        *,
        owner: str,
    ) -> tuple[ResourceRegistration, ...]:
        if not owner or owner != owner.strip():
            raise ValueError("resource owner must be a non-empty trimmed string")
        pending = tuple(bindings)
        claimed = set(self._paths)
        prepared: list[tuple[ResourceSpec, ResourceProvider, tuple[str, ...]]] = []
        for spec, provider in pending:
            if not isinstance(spec, ResourceSpec):
                raise TypeError("resource binding must contain ResourceSpec")
            for operation in ("inspect", "set", "delete"):
                if not callable(getattr(provider, operation, None)):
                    raise TypeError(f"resource provider must define {operation}")
            path = tuple(segment.casefold() for segment in spec.resource_path)
            if path in claimed:
                raise ValueError(f"resource path is already registered: {' '.join(path)}")
            claimed.add(path)
            prepared.append((spec, provider, path))
        command_bindings: list[CommandBinding] = []
        for spec, _provider, _path in prepared:
            command_bindings.extend(self._command_bindings(spec))
        commands = self._commands.register_many(command_bindings, owner=owner)

        registrations: list[ResourceRegistration] = []
        command_offset = 0
        for spec, provider, path in prepared:
            registration = ResourceRegistration(self._next_id, owner, spec)
            self._next_id += 1
            resource_commands = commands[command_offset : command_offset + 3]
            command_offset += 3
            self._resources[registration.id] = _RegisteredResource(registration, provider, resource_commands)
            self._paths[path] = registration.id
            registrations.append(registration)
        return tuple(registrations)

    def unregister(self, registration: ResourceRegistration) -> bool:
        registered = self._resources.get(registration.id)
        if registered is None or registered.registration != registration:
            return False
        del self._resources[registration.id]
        self._paths.pop(tuple(segment.casefold() for segment in registration.spec.resource_path), None)
        for command in reversed(registered.commands):
            self._commands.unregister(command)
        return True

    def snapshot(self) -> tuple[ResourceRegistration, ...]:
        return tuple(
            item.registration
            for item in sorted(
                self._resources.values(),
                key=lambda item: (
                    tuple(segment.casefold() for segment in item.registration.spec.resource_path),
                    item.registration.id,
                ),
            )
        )

    def resolve(self, path: Sequence[str]) -> ResourceRegistration | None:
        resource_id = self._paths.get(tuple(segment.casefold() for segment in path))
        return None if resource_id is None else self._resources[resource_id].registration

    async def inspect(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        *,
        actor_id: str | None = None,
    ) -> Mapping[str, object]:
        registered, principal = self._target(event, path, actor_id)
        result: dict[str, object] = {}
        for field in registered.registration.spec.fields:
            if not field.readable:
                continue
            self._authorize(event, principal, field, "inspect")
            result[field.name] = await _await_provider(registered.provider.inspect(principal, field))
        return result

    async def inspect_context(
        self,
        context: AuthorizationContext,
        path: Sequence[str],
    ) -> Mapping[str, object]:
        registered, principal = self._current_target(context, path)
        result: dict[str, object] = {}
        for field in registered.registration.spec.fields:
            if not field.readable:
                continue
            result[field.name] = await _await_provider(registered.provider.inspect(principal, field))
        return result

    async def set(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        field: str,
        value: str,
        *,
        actor_id: str | None = None,
    ) -> None:
        registered, principal = self._target(event, path, actor_id)
        selected = self._field(registered.registration.spec, field)
        if not selected.settable:
            raise ResourceError(f"resource field is not settable: {field}")
        self._authorize(event, principal, selected, "set")
        try:
            converted = selected.converter(value)
        except Exception as error:
            raise ResourceError(f"invalid value for resource field: {field}") from error
        await _await_provider(registered.provider.set(principal, selected, converted))

    async def set_context(
        self,
        context: AuthorizationContext,
        path: Sequence[str],
        field: str,
        value: str,
    ) -> None:
        registered, principal = self._current_target(context, path)
        selected = self._field(registered.registration.spec, field)
        if not selected.settable:
            raise ResourceError(f"resource field is not settable: {field}")
        try:
            converted = selected.converter(value)
        except Exception as error:
            raise ResourceError(f"invalid value for resource field: {field}") from error
        await _await_provider(registered.provider.set(principal, selected, converted))

    async def delete(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        field: str,
        *,
        actor_id: str | None = None,
    ) -> None:
        registered, principal = self._target(event, path, actor_id)
        selected = self._field(registered.registration.spec, field)
        if not selected.deletable:
            raise ResourceError(f"resource field is not deletable: {field}")
        self._authorize(event, principal, selected, "delete")
        await _await_provider(registered.provider.delete(principal, selected))

    async def delete_context(
        self,
        context: AuthorizationContext,
        path: Sequence[str],
        field: str,
    ) -> None:
        registered, principal = self._current_target(context, path)
        selected = self._field(registered.registration.spec, field)
        if not selected.deletable:
            raise ResourceError(f"resource field is not deletable: {field}")
        await _await_provider(registered.provider.delete(principal, selected))

    def _target(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        actor_id: str | None,
    ) -> tuple[_RegisteredResource, Principal]:
        resource_id = self._paths.get(tuple(segment.casefold() for segment in path))
        if resource_id is None:
            raise ResourceError(f"resource not found: {' '.join(path)}")
        if event.actor is None:
            raise ResourceError("resource operations require an actor")
        current = Principal(event.runtime_id, event.bot_id, event.actor.id)
        target = current if actor_id is None else Principal(event.runtime_id, event.bot_id, actor_id)
        return self._resources[resource_id], target

    def _current_target(
        self,
        context: AuthorizationContext,
        path: Sequence[str],
    ) -> tuple[_RegisteredResource, Principal]:
        resource_id = self._paths.get(tuple(segment.casefold() for segment in path))
        if resource_id is None:
            raise ResourceError(f"resource not found: {' '.join(path)}")
        if context.actor_id is None:
            raise ResourceError("resource operations require an actor")
        return self._resources[resource_id], Principal(context.runtime_id, context.bot_id, context.actor_id)

    def _authorize(
        self,
        event: EventEnvelope,
        target: Principal,
        field: ResourceField,
        operation: ResourceOperation,
    ) -> None:
        current = Principal(event.runtime_id, event.bot_id, event.actor.id) if event.actor is not None else None
        if current == target:
            return
        capability = field.capability_for(operation)
        if capability is None or not self._permissions.allows(event, capability):
            raise ResourceError(f"resource {operation} is not authorized for target")

    @staticmethod
    def _field(spec: ResourceSpec, name: str) -> ResourceField:
        for field in spec.fields:
            if field.name.casefold() == name.casefold():
                return field
        raise ResourceError(f"resource field not found: {name}")

    def _command_bindings(self, spec: ResourceSpec) -> tuple[CommandBinding, ...]:
        fields = "; ".join(f"{field.name}: {field.description}" for field in spec.fields if field.description)
        text = self._translator
        set_summary = text.text("resources.command.set_summary", "Set a {name} field", name=spec.name)
        if fields:
            set_summary += text.text("resources.command.fields", ". Fields: {fields}", fields=fields)

        async def inspect_command(invocation: CommandInvocation) -> HandlerResult:
            try:
                parsed = invocation.parse()
                actor_id = parsed.options["actor"]
                if actor_id is not None and not isinstance(actor_id, str):
                    raise RuntimeError("resource actor option must be a string")
                values = await self.inspect(invocation.event, spec.resource_path, actor_id=actor_id)
            except CommandParseError:
                return invocation.reply(
                    text.text("resources.error.invalid_arguments", "Invalid resource command arguments")
                )
            except ResourceError as error:
                return invocation.reply(_error_text(error, text))
            if not values:
                return invocation.reply(text.text("resources.error.no_readable_fields", "No readable resource fields"))
            return invocation.reply("\n".join(f"{name}: {value}" for name, value in values.items()))

        async def set_command(invocation: CommandInvocation) -> HandlerResult:
            try:
                parsed = invocation.parse()
                field = parsed.arguments["field"]
                value = parsed.arguments["value"]
                actor_id = parsed.options["actor"]
                if not all(isinstance(item, str) for item in (field, value)):
                    raise RuntimeError("resource command arguments must be strings")
                if actor_id is not None and not isinstance(actor_id, str):
                    raise RuntimeError("resource actor option must be a string")
                await self.set(
                    invocation.event,
                    spec.resource_path,
                    cast(str, field),
                    cast(str, value),
                    actor_id=actor_id,
                )
            except CommandParseError:
                return invocation.reply(
                    text.text("resources.error.invalid_arguments", "Invalid resource command arguments")
                )
            except ResourceError as error:
                return invocation.reply(_error_text(error, text))
            return invocation.reply(
                text.text(
                    "resources.command.updated",
                    "Updated {path}.{field}",
                    path=" ".join(spec.resource_path),
                    field=field,
                )
            )

        async def delete_command(invocation: CommandInvocation) -> HandlerResult:
            try:
                parsed = invocation.parse()
                field = parsed.arguments["field"]
                actor_id = parsed.options["actor"]
                if not isinstance(field, str):
                    raise RuntimeError("resource command field must be a string")
                if actor_id is not None and not isinstance(actor_id, str):
                    raise RuntimeError("resource actor option must be a string")
                await self.delete(invocation.event, spec.resource_path, field, actor_id=actor_id)
            except CommandParseError:
                return invocation.reply(
                    text.text("resources.error.invalid_arguments", "Invalid resource command arguments")
                )
            except ResourceError as error:
                return invocation.reply(_error_text(error, text))
            return invocation.reply(
                text.text(
                    "resources.command.reset",
                    "Reset {path}.{field}",
                    path=" ".join(spec.resource_path),
                    field=field,
                )
            )

        actor_option = OptionSpec("actor", aliases=("a",), required=False, default=None)
        return (
            (
                CommandSpec(
                    spec.name,
                    path=spec.path,
                    summary=spec.summary,
                    schema=CommandSchema(options=(actor_option,)),
                ),
                inspect_command,
            ),
            (
                CommandSpec(
                    "set",
                    path=spec.resource_path,
                    summary=set_summary,
                    schema=CommandSchema(
                        arguments=(ArgumentSpec("field"), ArgumentSpec("value")),
                        options=(actor_option,),
                    ),
                ),
                set_command,
            ),
            (
                CommandSpec(
                    "delete",
                    path=spec.resource_path,
                    summary=text.text(
                        "resources.command.reset_summary",
                        "Reset a {name} field to its default",
                        name=spec.name,
                    ),
                    schema=CommandSchema(
                        arguments=(ArgumentSpec("field"),),
                        options=(actor_option,),
                    ),
                ),
                delete_command,
            ),
        )


async def _await_provider(value: object) -> object:
    if not inspect.isawaitable(value):
        raise TypeError("resource provider operation must return an awaitable")
    return await value


def _error_text(error: ResourceError, translator: Translator) -> str:
    return translator.text("resources.error.request_failed", "Resource request failed: {error}", error=error)


def create_resource_service(
    permissions: PermissionService,
    commands: CommandService,
    translator: Translator,
) -> ResourceService:
    return _ResourceService(permissions, commands, translator)


__all__ = ["RESOURCE_SERVICE", "ResourceError", "ResourceService", "create_resource_service"]
