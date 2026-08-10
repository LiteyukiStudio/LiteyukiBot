"""Permission identities, capability grants, and access checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from liteyukibot.events import EventEnvelope
from liteyukibot.services import ServiceKey

PUBLIC = "public"
PERMISSION_SERVICE = ServiceKey("liteyukibot.permissions", 1)


def _validate_token(kind: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"permission {kind} must be a string")
    if not value or value != value.strip() or any(character.isspace() for character in value):
        raise ValueError(f"permission {kind} must be a non-empty token without whitespace")
    return value


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


@dataclass(frozen=True, slots=True)
class PermissionSnapshot:
    principal: Principal | None
    roles: frozenset[str]
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        roles = frozenset(self.roles)
        capabilities = frozenset(self.capabilities)
        for role in roles:
            _validate_token("snapshot role", role)
        for capability in capabilities:
            _validate_token("snapshot capability", capability)
        if PUBLIC not in capabilities:
            raise ValueError("permission snapshot must include public capability")
        object.__setattr__(self, "roles", roles)
        object.__setattr__(self, "capabilities", capabilities)

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
        return Principal(
            runtime_id=event.runtime_id,
            bot_id=event.bot_id,
            actor_id=event.actor.id,
        )

    def resolve(self, event: EventEnvelope) -> PermissionSnapshot:
        principal = self.principal(event)
        if principal is None:
            return self._anonymous
        return self._snapshots.get(
            principal,
            PermissionSnapshot(principal, frozenset(), frozenset({PUBLIC})),
        )

    def allows(self, event: EventEnvelope, capability: str) -> bool:
        if not isinstance(capability, str):
            return False
        if not capability or capability != capability.strip() or any(character.isspace() for character in capability):
            return False
        return self.resolve(event).allows(capability)


def _parse_token_sequence(value: object, *, location: str, kind: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"permission {location} must be a sequence of strings")
    parsed: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        token = _validate_token(f"{location}[{index}] {kind}", item)
        if token in seen:
            raise ValueError(f"permission {location}[{index}] duplicates {kind} {token}")
        seen.add(token)
        parsed.append(token)
    return tuple(parsed)


def _parse_roles(value: object) -> dict[str, frozenset[str]]:
    if not isinstance(value, Mapping):
        raise TypeError("permission roles must be an object")
    roles: dict[str, frozenset[str]] = {}
    for raw_name, raw_capabilities in value.items():
        name = _validate_token("role name", raw_name)
        capabilities = _parse_token_sequence(
            raw_capabilities,
            location=f"roles.{name}",
            kind="capability",
        )
        if not capabilities:
            raise ValueError(f"permission role {name} must contain at least one capability")
        if PUBLIC in capabilities:
            raise ValueError(f"permission role {name} must not grant reserved capability {PUBLIC}")
        roles[name] = frozenset(capabilities)
    return roles


def _invalid_fields(location: str, actual: set[object], required: set[str], optional: set[str]) -> ValueError:
    missing = sorted(required - actual)
    extra = sorted(str(item) for item in actual - required - optional)
    details: list[str] = []
    if missing:
        details.append(f"missing {', '.join(missing)}")
    if extra:
        details.append(f"unknown {', '.join(extra)}")
    return ValueError(f"permission {location} has invalid fields: {'; '.join(details)}")


def _parse_grants(
    value: object,
    roles: Mapping[str, frozenset[str]],
) -> dict[Principal, PermissionSnapshot]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError("permission grants must be a sequence of objects")
    snapshots: dict[Principal, PermissionSnapshot] = {}
    required = {"runtime_id", "bot_id", "actor_id"}
    optional = {"roles", "capabilities"}
    for index, raw_grant in enumerate(value):
        location = f"grants[{index}]"
        if not isinstance(raw_grant, Mapping):
            raise TypeError(f"permission {location} must be an object")
        actual = set(raw_grant)
        invalid_fields = (
            not all(isinstance(field, str) for field in actual)
            or not required <= actual
            or bool(actual - required - optional)
        )
        if invalid_fields:
            raise _invalid_fields(location, actual, required, optional)

        principal = Principal(
            runtime_id=raw_grant["runtime_id"],
            bot_id=raw_grant["bot_id"],
            actor_id=raw_grant["actor_id"],
        )
        if principal in snapshots:
            raise ValueError(f"permission {location} duplicates an earlier principal")

        assigned_roles = _parse_token_sequence(
            raw_grant.get("roles", ()),
            location=f"{location}.roles",
            kind="role",
        )
        direct_capabilities = _parse_token_sequence(
            raw_grant.get("capabilities", ()),
            location=f"{location}.capabilities",
            kind="capability",
        )
        if not assigned_roles and not direct_capabilities:
            raise ValueError(f"permission {location} must assign at least one role or capability")
        unknown_roles = sorted(set(assigned_roles) - roles.keys())
        if unknown_roles:
            raise ValueError(f"permission {location} references unknown roles: {', '.join(unknown_roles)}")
        if PUBLIC in direct_capabilities:
            raise ValueError(f"permission {location} must not grant reserved capability {PUBLIC}")

        capabilities = {PUBLIC, *direct_capabilities}
        for role in assigned_roles:
            capabilities.update(roles[role])
        snapshots[principal] = PermissionSnapshot(
            principal=principal,
            roles=frozenset(assigned_roles),
            capabilities=frozenset(capabilities),
        )
    return snapshots


def create_permission_service(config: Mapping[str, Any]) -> PermissionService:
    if not all(isinstance(key, str) for key in config):
        raise TypeError("permission config keys must be strings")
    unknown = set(config) - {"roles", "grants"}
    if unknown:
        raise ValueError(f"unknown permission config keys: {', '.join(sorted(unknown))}")
    roles = _parse_roles(config.get("roles", {}))
    snapshots = _parse_grants(config.get("grants", ()), roles)
    return _ConfiguredPermissionService(snapshots)


__all__ = [
    "PERMISSION_SERVICE",
    "PUBLIC",
    "PermissionService",
    "PermissionSnapshot",
    "Principal",
]
