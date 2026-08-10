"""Resource registry and principal-aware operation dispatch."""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from liteyukibot_permissions import PermissionService, Principal

from liteyukibot.events import EventEnvelope
from liteyukibot.services import ServiceKey

from .models import ResourceField, ResourceOperation, ResourceProvider, ResourceRegistration, ResourceSpec

RESOURCE_SERVICE = ServiceKey("liteyukibot.resources", 1)


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


@dataclass(frozen=True, slots=True)
class _RegisteredResource:
    registration: ResourceRegistration
    provider: ResourceProvider


class _ResourceService:
    def __init__(self, permissions: PermissionService) -> None:
        self._permissions = permissions
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
        registrations: list[ResourceRegistration] = []
        for spec, provider, path in prepared:
            registration = ResourceRegistration(self._next_id, owner, spec)
            self._next_id += 1
            self._resources[registration.id] = _RegisteredResource(registration, provider)
            self._paths[path] = registration.id
            registrations.append(registration)
        return tuple(registrations)

    def unregister(self, registration: ResourceRegistration) -> bool:
        registered = self._resources.get(registration.id)
        if registered is None or registered.registration != registration:
            return False
        del self._resources[registration.id]
        self._paths.pop(tuple(segment.casefold() for segment in registration.spec.resource_path), None)
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


async def _await_provider(value: object) -> object:
    if not inspect.isawaitable(value):
        raise TypeError("resource provider operation must return an awaitable")
    return await value


def create_resource_service(permissions: PermissionService) -> ResourceService:
    return _ResourceService(permissions)


__all__ = ["RESOURCE_SERVICE", "ResourceError", "ResourceService", "create_resource_service"]
