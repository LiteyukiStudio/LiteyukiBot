"""Package-owned initialization metadata for CLI and future configuration UIs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class InitFieldKind(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    STRING_LIST = "string_list"
    SECRET = "secret"


@dataclass(frozen=True, slots=True)
class InitFieldSpec:
    """One package-owned configuration field safe for generic setup clients."""

    key: str
    label: str
    kind: InitFieldKind
    default: Any = None
    required: bool = False
    description: str = ""
    choices: tuple[str, ...] = ()
    secret_environment: str | None = None

    def __post_init__(self) -> None:
        if not self.key or self.key != self.key.strip() or "." in self.key:
            raise ValueError("initialization field key must be a non-empty simple identifier")
        if not self.label.strip():
            raise ValueError("initialization field label must not be blank")
        if self.kind is InitFieldKind.SECRET:
            if not self.secret_environment or self.secret_environment != self.secret_environment.strip():
                raise ValueError("secret initialization fields require a target environment variable")
        elif self.secret_environment is not None:
            raise ValueError("only secret initialization fields may declare a target environment variable")
        if len(set(self.choices)) != len(self.choices) or any(not item for item in self.choices):
            raise ValueError("initialization field choices must be unique non-empty strings")


@dataclass(frozen=True, slots=True)
class PluginInitSpec:
    description: str = ""
    fields: tuple[InitFieldSpec, ...] = ()

    def __post_init__(self) -> None:
        _validate_fields(self.fields)


@dataclass(frozen=True, slots=True)
class RuntimeInitSpec:
    default_id: str
    description: str = ""
    default_options: Mapping[str, Any] = field(default_factory=dict)
    fields: tuple[InitFieldSpec, ...] = ()

    def __post_init__(self) -> None:
        if not self.default_id or self.default_id != self.default_id.strip():
            raise ValueError("runtime initialization default_id must be a non-empty trimmed string")
        _validate_fields(self.fields)
        object.__setattr__(self, "default_options", MappingProxyType(dict(self.default_options)))


def _validate_fields(fields: tuple[InitFieldSpec, ...]) -> None:
    if len({field.key for field in fields}) != len(fields):
        raise ValueError("initialization field keys must be unique")


type InitValue = str | int | bool | tuple[str, ...] | None
type InitValues = Mapping[str, InitValue]


__all__ = [
    "InitFieldKind",
    "InitFieldSpec",
    "InitValue",
    "InitValues",
    "PluginInitSpec",
    "RuntimeInitSpec",
]
