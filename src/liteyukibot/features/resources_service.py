"""Resource registry and principal-aware operation dispatch."""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from liteyukibot_kernel.events import EventEnvelope, HandlerResult
from liteyukibot_kernel.services import ServiceKey

from liteyukibot.i18n import Translator

from .commands_models import CommandBinding, CommandInvocation, CommandRegistration, CommandSpec
from .commands_parsing import ArgumentSpec, CommandParseError, CommandSchema, OptionSpec
from .commands_service import CommandService
from .permissions import PermissionService, Principal
from .resources_models import ResourceField, ResourceOperation, ResourceProvider, ResourceRegistration, ResourceSpec

RESOURCE_SERVICE = ServiceKey("liteyukibot.resources", 2)


class ResourceError(ValueError):
    """Raised when a resource operation cannot be performed."""


class ResourceService(Protocol):
    """Define the structural interface required from a resource service."""
    def register(
        self,
        spec: ResourceSpec,
        provider: ResourceProvider,
        *,
        owner: str,
    ) -> ResourceRegistration:
        """Register the resource service operation.

        Args:
            spec: The spec value used by the operation.
            provider: The provider value used by the operation.
            owner: Stable owner identity for the registration.

        Returns:
            The `ResourceRegistration` result produced by the operation.
        """
        ...

    def register_many(
        self,
        bindings: Sequence[tuple[ResourceSpec, ResourceProvider]],
        *,
        owner: str,
    ) -> tuple[ResourceRegistration, ...]:
        """Register many.

        Args:
            bindings: The bindings value used by the operation.
            owner: Stable owner identity for the registration.

        Returns:
            The `tuple[ResourceRegistration, ...]` result produced by the operation.
        """
        ...

    def unregister(self, registration: ResourceRegistration) -> bool:
        """Unregister the resource service operation.

        Args:
            registration: The registration value used by the operation.

        Returns:
            Whether the requested condition is satisfied.
        """
        ...

    def snapshot(self) -> tuple[ResourceRegistration, ...]:
        """Return an immutable snapshot of the resource service state.

        Returns:
            The requested `tuple[ResourceRegistration, ...]` value.
        """
        ...

    def resolve(self, path: Sequence[str]) -> ResourceRegistration | None:
        """Resolve the resource service operation.

        Args:
            path: Filesystem or logical resource path.

        Returns:
            The requested `ResourceRegistration | None` value.
        """
        ...

    async def inspect(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        *,
        actor_id: str | None = None,
    ) -> Mapping[str, object]:
        """Inspect the resource service operation.

        Args:
            event: Event associated with the operation.
            path: Filesystem or logical resource path.
            actor_id: Stable identifier for the actor.

        Returns:
            The `Mapping[str, object]` result produced by the operation.
        """
        ...

    async def set(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        field: str,
        value: str,
        *,
        actor_id: str | None = None,
    ) -> None:
        """Set the resource service operation.

        Args:
            event: Event associated with the operation.
            path: Filesystem or logical resource path.
            field: The field value used by the operation.
            value: Value to validate, transform, or store.
            actor_id: Stable identifier for the actor.

        Returns:
            None.
        """
        ...

    async def delete(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        field: str,
        *,
        actor_id: str | None = None,
    ) -> None:
        """Delete the resource service operation.

        Args:
            event: Event associated with the operation.
            path: Filesystem or logical resource path.
            field: The field value used by the operation.
            actor_id: Stable identifier for the actor.

        Returns:
            None.
        """
        ...


@dataclass(frozen=True, slots=True)
class _RegisteredResource:
    """Represent the registered resource contract."""
    registration: ResourceRegistration
    provider: ResourceProvider
    commands: tuple[CommandRegistration, ...]


class _ResourceService:
    """Represent the resource service contract."""
    def __init__(self, permissions: PermissionService, commands: CommandService, translator: Translator) -> None:
        """Initialize the resource service.

        Args:
            permissions: The permissions value used by the operation.
            commands: The commands value used by the operation.
            translator: The translator value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_ResourceService.__init__`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
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
        """Register the resource service operation.

        Args:
            spec: The spec value used by the operation.
            provider: The provider value used by the operation.
            owner: Stable owner identity for the registration.

        Returns:
            The `ResourceRegistration` result produced by the operation.

        Notes:
            Internal implementation detail for `_ResourceService.register`. It delegates to `register_many`
            while keeping intermediate state local to the owning operation.
        """
        return self.register_many(((spec, provider),), owner=owner)[0]

    def register_many(
        self,
        bindings: Sequence[tuple[ResourceSpec, ResourceProvider]],
        *,
        owner: str,
    ) -> tuple[ResourceRegistration, ...]:
        """Register many.

        Args:
            bindings: The bindings value used by the operation.
            owner: Stable owner identity for the registration.

        Returns:
            The `tuple[ResourceRegistration, ...]` result produced by the operation.

        Notes:
            Internal implementation detail for `_ResourceService.register_many`. It delegates to `strip`,
            `callable`, `getattr`, `casefold` while keeping intermediate state local to the owning
            operation.
        """
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
        """Unregister the resource service operation.

        Args:
            registration: The registration value used by the operation.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `_ResourceService.unregister`. It delegates to `get`, `pop`,
            `casefold`, `reversed` while keeping intermediate state local to the owning operation.
        """
        registered = self._resources.get(registration.id)
        if registered is None or registered.registration != registration:
            return False
        del self._resources[registration.id]
        self._paths.pop(tuple(segment.casefold() for segment in registration.spec.resource_path), None)
        for command in reversed(registered.commands):
            self._commands.unregister(command)
        return True

    def snapshot(self) -> tuple[ResourceRegistration, ...]:
        """Return an immutable snapshot of the resource service state.

        Returns:
            The requested `tuple[ResourceRegistration, ...]` value.

        Notes:
            Internal implementation detail for `_ResourceService.snapshot`. It delegates to `sorted`,
            `values`, `casefold` while keeping intermediate state local to the owning operation.
        """
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
        """Resolve the resource service operation.

        Args:
            path: Filesystem or logical resource path.

        Returns:
            The requested `ResourceRegistration | None` value.

        Notes:
            Internal implementation detail for `_ResourceService.resolve`. It delegates to `get`, `casefold`
            while keeping intermediate state local to the owning operation.
        """
        resource_id = self._paths.get(tuple(segment.casefold() for segment in path))
        return None if resource_id is None else self._resources[resource_id].registration

    async def inspect(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        *,
        actor_id: str | None = None,
    ) -> Mapping[str, object]:
        """Inspect the resource service operation.

        Args:
            event: Event associated with the operation.
            path: Filesystem or logical resource path.
            actor_id: Stable identifier for the actor.

        Returns:
            The `Mapping[str, object]` result produced by the operation.

        Notes:
            Internal implementation detail for `_ResourceService.inspect`. It delegates to `_target`,
            `_authorize`, `_await_provider`, `inspect` while keeping intermediate state local to the owning
            operation.
        """
        registered, principal = self._target(event, path, actor_id)
        result: dict[str, object] = {}
        for field in registered.registration.spec.fields:
            if not field.readable:
                continue
            self._authorize(event, principal, field, "inspect")
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
        """Set the resource service operation.

        Args:
            event: Event associated with the operation.
            path: Filesystem or logical resource path.
            field: The field value used by the operation.
            value: Value to validate, transform, or store.
            actor_id: Stable identifier for the actor.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_ResourceService.set`. It delegates to `_target`, `_field`,
            `_authorize`, `converter` while keeping intermediate state local to the owning operation.
        """
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

    async def delete(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        field: str,
        *,
        actor_id: str | None = None,
    ) -> None:
        """Delete the resource service operation.

        Args:
            event: Event associated with the operation.
            path: Filesystem or logical resource path.
            field: The field value used by the operation.
            actor_id: Stable identifier for the actor.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_ResourceService.delete`. It delegates to `_target`,
            `_field`, `_authorize`, `_await_provider` while keeping intermediate state local to the owning
            operation.
        """
        registered, principal = self._target(event, path, actor_id)
        selected = self._field(registered.registration.spec, field)
        if not selected.deletable:
            raise ResourceError(f"resource field is not deletable: {field}")
        self._authorize(event, principal, selected, "delete")
        await _await_provider(registered.provider.delete(principal, selected))

    def _target(
        self,
        event: EventEnvelope,
        path: Sequence[str],
        actor_id: str | None,
    ) -> tuple[_RegisteredResource, Principal]:
        """Implement the target operation for the resource service.

        Args:
            event: Event associated with the operation.
            path: Filesystem or logical resource path.
            actor_id: Stable identifier for the actor.

        Returns:
            The `tuple[_RegisteredResource, Principal]` result produced by the operation.

        Notes:
            Internal implementation detail for `_ResourceService._target`. It delegates to `get`,
            `casefold`, `join` while keeping intermediate state local to the owning operation.
        """
        resource_id = self._paths.get(tuple(segment.casefold() for segment in path))
        if resource_id is None:
            raise ResourceError(f"resource not found: {' '.join(path)}")
        if event.actor is None:
            raise ResourceError("resource operations require an actor")
        current = Principal(event.runtime_id, event.bot_id, event.actor.id)
        target = current if actor_id is None else Principal(event.runtime_id, event.bot_id, actor_id)
        return self._resources[resource_id], target

    def _authorize(
        self,
        event: EventEnvelope,
        target: Principal,
        field: ResourceField,
        operation: ResourceOperation,
    ) -> None:
        """Authorize the resource service operation.

        Args:
            event: Event associated with the operation.
            target: Target value or location for the operation.
            field: The field value used by the operation.
            operation: The operation value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_ResourceService._authorize`. It delegates to
            `capability_for`, `allows` while keeping intermediate state local to the owning operation.
        """
        current = Principal(event.runtime_id, event.bot_id, event.actor.id) if event.actor is not None else None
        if current == target:
            return
        capability = field.capability_for(operation)
        if capability is None or not self._permissions.allows(event, capability):
            raise ResourceError(f"resource {operation} is not authorized for target")

    @staticmethod
    def _field(spec: ResourceSpec, name: str) -> ResourceField:
        """Implement the field operation for the resource service.

        Args:
            spec: The spec value used by the operation.
            name: Stable name used to identify the value.

        Returns:
            The `ResourceField` result produced by the operation.

        Notes:
            Internal implementation detail for `_ResourceService._field`. It delegates to `casefold` while
            keeping intermediate state local to the owning operation.
        """
        for field in spec.fields:
            if field.name.casefold() == name.casefold():
                return field
        raise ResourceError(f"resource field not found: {name}")

    def _command_bindings(self, spec: ResourceSpec) -> tuple[CommandBinding, ...]:
        """Implement the command bindings operation for the resource service.

        Args:
            spec: The spec value used by the operation.

        Returns:
            The `tuple[CommandBinding, ...]` result produced by the operation.

        Notes:
            Internal implementation detail for `_ResourceService._command_bindings`. It delegates to `join`,
            `text` while keeping intermediate state local to the owning operation.
        """
        fields = "; ".join(f"{field.name}: {field.description}" for field in spec.fields if field.description)
        text = self._translator
        set_summary = text.text("resources.command.set_summary", "Set a {name} field", name=spec.name)
        if fields:
            set_summary += text.text("resources.command.fields", ". Fields: {fields}", fields=fields)

        async def inspect_command(invocation: CommandInvocation) -> HandlerResult:
            """Inspect command.

            Args:
                invocation: The invocation value used by the operation.

            Returns:
                The `HandlerResult` result produced by the operation.

            Notes:
                Internal implementation detail for `_ResourceService._command_bindings.inspect_command`. It
                delegates to `parse`, `inspect`, `reply`, `text` while keeping intermediate state local to the
                owning operation.
            """
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
            """Set command.

            Args:
                invocation: The invocation value used by the operation.

            Returns:
                The `HandlerResult` result produced by the operation.

            Notes:
                Internal implementation detail for `_ResourceService._command_bindings.set_command`. It
                delegates to `parse`, `all`, `cast`, `reply` while keeping intermediate state local to the
                owning operation.
            """
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
            """Delete command.

            Args:
                invocation: The invocation value used by the operation.

            Returns:
                The `HandlerResult` result produced by the operation.

            Notes:
                Internal implementation detail for `_ResourceService._command_bindings.delete_command`. It
                delegates to `parse`, `delete`, `reply`, `text` while keeping intermediate state local to the
                owning operation.
            """
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
    """Implement the await provider operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `object` result produced by the operation.

    Notes:
        Internal implementation detail for `_await_provider`. It delegates to `isawaitable` while
        keeping intermediate state local to the owning operation.
    """
    if not inspect.isawaitable(value):
        raise TypeError("resource provider operation must return an awaitable")
    return await value


def _error_text(error: ResourceError, translator: Translator) -> str:
    """Implement the error text operation for the component.

    Args:
        error: The error value used by the operation.
        translator: The translator value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_error_text`. It delegates to `text` while keeping
        intermediate state local to the owning operation.
    """
    return translator.text("resources.error.request_failed", "Resource request failed: {error}", error=error)


def create_resource_service(
    permissions: PermissionService,
    commands: CommandService,
    translator: Translator,
) -> ResourceService:
    """Create resource service.

    Args:
        permissions: The permissions value used by the operation.
        commands: The commands value used by the operation.
        translator: The translator value used by the operation.

    Returns:
        The `ResourceService` result produced by the operation.
    """
    return _ResourceService(permissions, commands, translator)


__all__ = ["RESOURCE_SERVICE", "ResourceError", "ResourceService", "create_resource_service"]
