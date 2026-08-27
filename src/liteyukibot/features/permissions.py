"""Principal capability grants for commands and resources."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from liteyukibot_cordis import Scope
from liteyukibot_kernel import EventEnvelope, ServiceKey

from .common import publish_service

PUBLIC = "public"
PERMISSION_SERVICE = ServiceKey("liteyukibot.permissions", 2)

def _token(value: object, location: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character.isspace() for character in value)
    ):
        raise ValueError(f"permission {location} must be a non-empty token without whitespace")
    return value


def _tokens(value: object, location: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"permission {location} must be a sequence of strings")
    result = tuple(_token(item, f"{location}[{index}]") for index, item in enumerate(value))
    if len(set(result)) != len(result):
        raise ValueError(f"permission {location} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class Principal:
    runtime_id: str
    bot_id: str
    actor_id: str

    def __post_init__(self) -> None:
        for name in ("runtime_id", "bot_id", "actor_id"):
            object.__setattr__(self, name, _token(getattr(self, name), f"principal {name}"))


@dataclass(frozen=True, slots=True)
class PermissionSnapshot:
    principal: Principal | None
    roles: frozenset[str]
    capabilities: frozenset[str]

    def allows(self, capability: str) -> bool:
        return capability in self.capabilities


class PermissionService(Protocol):
    def principal(self, event: EventEnvelope) -> Principal | None: ...

    def resolve(self, event: EventEnvelope) -> PermissionSnapshot: ...

    def allows(self, event: EventEnvelope, capability: str) -> bool: ...


class _ConfiguredPermissionService:
    def __init__(self, snapshots: Mapping[Principal, PermissionSnapshot]) -> None:
        self._snapshots = dict(snapshots)
        self._anonymous = PermissionSnapshot(None, frozenset(), frozenset({PUBLIC}))

    def principal(self, event: EventEnvelope) -> Principal | None:
        if event.actor is None:
            return None
        return Principal(event.runtime_id, event.bot_id, event.actor.id)

    def resolve(self, event: EventEnvelope) -> PermissionSnapshot:
        principal = self.principal(event)
        if principal is None:
            return self._anonymous
        return self._snapshots.get(
            principal,
            PermissionSnapshot(principal, frozenset(), frozenset({PUBLIC})),
        )

    def allows(self, event: EventEnvelope, capability: str) -> bool:
        try:
            capability = _token(capability, "capability")
        except ValueError:
            return False
        return self.resolve(event).allows(capability)


def _parse_roles(value: object) -> dict[str, frozenset[str]]:
    if not isinstance(value, Mapping):
        raise TypeError("permission roles must be an object")
    roles: dict[str, frozenset[str]] = {}
    for raw_name, raw_capabilities in value.items():
        name = _token(raw_name, "role name")
        capabilities = frozenset(_tokens(raw_capabilities, f"roles.{name}"))
        if not capabilities:
            raise ValueError(f"permission role {name} must contain at least one capability")
        if PUBLIC in capabilities:
            raise ValueError(f"permission role {name} must not grant reserved capability {PUBLIC}")
        roles[name] = capabilities
    return roles


def _parse_grants(value: object, roles: Mapping[str, frozenset[str]]) -> dict[Principal, PermissionSnapshot]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError("permission grants must be a sequence of objects")
    snapshots: dict[Principal, PermissionSnapshot] = {}
    allowed_fields = {"runtime_id", "bot_id", "actor_id", "roles", "capabilities"}
    for index, raw in enumerate(value):
        location = f"grants[{index}]"
        if not isinstance(raw, Mapping):
            raise TypeError(f"permission {location} must be an object")
        if set(raw) - allowed_fields or not {"runtime_id", "bot_id", "actor_id"} <= set(raw):
            raise ValueError(f"permission {location} has invalid fields")
        principal = Principal(
            runtime_id=_token(raw["runtime_id"], f"{location}.runtime_id"),
            bot_id=_token(raw["bot_id"], f"{location}.bot_id"),
            actor_id=_token(raw["actor_id"], f"{location}.actor_id"),
        )
        if principal in snapshots:
            raise ValueError(f"permission {location} duplicates an earlier principal")
        assigned_roles = _tokens(raw.get("roles", ()), f"{location}.roles")
        direct = _tokens(raw.get("capabilities", ()), f"{location}.capabilities")
        if not assigned_roles and not direct:
            raise ValueError(f"permission {location} must assign a role or capability")
        unknown = set(assigned_roles) - roles.keys()
        if unknown:
            raise ValueError(f"permission {location} references unknown roles: {', '.join(sorted(unknown))}")
        if PUBLIC in direct:
            raise ValueError(f"permission {location} must not grant reserved capability {PUBLIC}")
        capabilities = {PUBLIC, *direct}
        for role in assigned_roles:
            capabilities.update(roles[role])
        snapshots[principal] = PermissionSnapshot(
            principal,
            frozenset(assigned_roles),
            frozenset(capabilities),
        )
    return snapshots


def create_permission_service(config: Mapping[str, Any]) -> PermissionService:
    unknown = set(config) - {"roles", "grants"}
    if unknown:
        raise ValueError(f"unknown permission config keys: {', '.join(sorted(unknown))}")
    roles = _parse_roles(config.get("roles", {}))
    return _ConfiguredPermissionService(_parse_grants(config.get("grants", ()), roles))


async def activate(scope: Scope) -> None:
    await publish_service(scope, PERMISSION_SERVICE, create_permission_service(scope.config))


__all__ = [
    "PERMISSION_SERVICE",
    "PUBLIC",
    "PermissionService",
    "PermissionSnapshot",
    "Principal",
    "activate",
    "create_permission_service",
]
