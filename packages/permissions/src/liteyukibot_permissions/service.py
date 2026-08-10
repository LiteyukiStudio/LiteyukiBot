"""Permission identities and access checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from liteyukibot.events import EventEnvelope
from liteyukibot.services import ServiceKey

PUBLIC = "public"
OPERATOR = "operator"
PERMISSION_SERVICE = ServiceKey("liteyukibot.permissions", 1)


class _Logger(Protocol):
    def warning(self, message: str, *args: Any, **kwargs: Any) -> None: ...


@dataclass(frozen=True, slots=True)
class Principal:
    runtime_id: str
    bot_id: str
    actor_id: str

    def __post_init__(self) -> None:
        for name, value in (
            ("runtime_id", self.runtime_id),
            ("bot_id", self.bot_id),
            ("actor_id", self.actor_id),
        ):
            if not isinstance(value, str):
                raise TypeError(f"principal {name} must be a string")
            if not value or value != value.strip():
                raise ValueError(f"principal {name} must be a non-empty trimmed string")


class PermissionService(Protocol):
    def principal(self, event: EventEnvelope) -> Principal | None: ...

    def allows(self, event: EventEnvelope, permission: str) -> bool: ...


class _ConfiguredPermissionService:
    def __init__(self, operators: frozenset[Principal], logger: _Logger) -> None:
        self._operators = operators
        self._logger = logger

    def principal(self, event: EventEnvelope) -> Principal | None:
        if event.actor is None:
            return None
        return Principal(
            runtime_id=event.runtime_id,
            bot_id=event.bot_id,
            actor_id=event.actor.id,
        )

    def allows(self, event: EventEnvelope, permission: str) -> bool:
        if permission == PUBLIC:
            return True
        if permission == OPERATOR:
            principal = self.principal(event)
            return principal is not None and principal in self._operators
        self._logger.warning(
            "unknown permission {} denied",
            permission,
            event_id=event.id,
            runtime=event.runtime_id,
            bot_id=event.bot_id,
        )
        return False


def create_permission_service(
    config: Mapping[str, Any],
    logger: _Logger,
) -> PermissionService:
    unknown = set(config) - {"operators"}
    if unknown:
        raise ValueError(f"unknown permission config keys: {', '.join(sorted(unknown))}")

    raw_operators = config.get("operators", ())
    if not isinstance(raw_operators, Sequence) or isinstance(raw_operators, (str, bytes)):
        raise TypeError("permission operators must be a sequence of objects")

    operators: set[Principal] = set()
    for index, raw_operator in enumerate(raw_operators):
        if not isinstance(raw_operator, Mapping):
            raise TypeError(f"permission operators[{index}] must be an object")
        expected = {"runtime_id", "bot_id", "actor_id"}
        actual = set(raw_operator)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            details: list[str] = []
            if missing:
                details.append(f"missing {', '.join(missing)}")
            if extra:
                details.append(f"unknown {', '.join(extra)}")
            raise ValueError(f"permission operators[{index}] has invalid fields: {'; '.join(details)}")
        values = {name: raw_operator[name] for name in expected}
        if any(not isinstance(value, str) for value in values.values()):
            raise TypeError(f"permission operators[{index}] fields must be strings")
        principal = Principal(**values)
        if principal in operators:
            raise ValueError(f"permission operators[{index}] duplicates an earlier identity")
        operators.add(principal)
    return _ConfiguredPermissionService(frozenset(operators), logger)


__all__ = [
    "OPERATOR",
    "PERMISSION_SERVICE",
    "PUBLIC",
    "PermissionService",
    "Principal",
]
