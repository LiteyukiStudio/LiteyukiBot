"""Public resource declaration and provider contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from liteyukibot_permissions import Principal

type ResourceOperation = Literal["inspect", "set", "delete"]
type ResourceConverter = Callable[[str], object]


def _token(kind: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"resource {kind} must be a string")
    if not value or value != value.strip() or any(character.isspace() for character in value):
        raise ValueError(f"resource {kind} must be a non-empty token without whitespace")
    return value


@dataclass(frozen=True, slots=True)
class ResourceField:
    name: str
    converter: ResourceConverter
    description: str = ""
    readable: bool = True
    settable: bool = True
    deletable: bool = True
    inspect_capability: str | None = None
    set_capability: str | None = None
    delete_capability: str | None = None

    def __post_init__(self) -> None:
        _token("field name", self.name)
        if not callable(self.converter):
            raise TypeError(f"resource field {self.name} converter must be callable")
        if not isinstance(self.description, str):
            raise TypeError(f"resource field {self.name} description must be a string")
        for operation, enabled in (
            ("readable", self.readable),
            ("settable", self.settable),
            ("deletable", self.deletable),
        ):
            if not isinstance(enabled, bool):
                raise TypeError(f"resource field {self.name} {operation} must be a boolean")
        for operation, capability in (
            ("inspect", self.inspect_capability),
            ("set", self.set_capability),
            ("delete", self.delete_capability),
        ):
            if capability is not None:
                _token(f"field {self.name} {operation} capability", capability)
        if not any((self.readable, self.settable, self.deletable)):
            raise ValueError(f"resource field {self.name} must enable at least one operation")

    def capability_for(self, operation: ResourceOperation) -> str | None:
        return {
            "inspect": self.inspect_capability,
            "set": self.set_capability,
            "delete": self.delete_capability,
        }[operation]


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    name: str
    path: tuple[str, ...] = ()
    summary: str = ""
    fields: tuple[ResourceField, ...] = ()

    def __post_init__(self) -> None:
        _token("name", self.name)
        if isinstance(self.path, str):
            raise TypeError("resource path must be a sequence of tokens")
        path = tuple(self.path)
        for segment in path:
            _token("path segment", segment)
        if not isinstance(self.summary, str):
            raise TypeError("resource summary must be a string")
        if any(not isinstance(field, ResourceField) for field in self.fields):
            raise TypeError("resource fields must contain ResourceField values")
        fields = tuple(self.fields)
        names = [field.name.casefold() for field in fields]
        if len(names) != len(set(names)):
            raise ValueError(f"resource {self.name} fields must not contain duplicates")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "fields", fields)

    @property
    def resource_path(self) -> tuple[str, ...]:
        return (*self.path, self.name)


class ResourceProvider(Protocol):
    def inspect(self, principal: Principal, field: ResourceField) -> Awaitable[object]: ...

    def set(self, principal: Principal, field: ResourceField, value: object) -> Awaitable[None]: ...

    def delete(self, principal: Principal, field: ResourceField) -> Awaitable[None]: ...


@dataclass(frozen=True, slots=True)
class ResourceRegistration:
    id: int
    owner: str
    spec: ResourceSpec


__all__ = [
    "ResourceConverter",
    "ResourceField",
    "ResourceOperation",
    "ResourceProvider",
    "ResourceRegistration",
    "ResourceSpec",
]
