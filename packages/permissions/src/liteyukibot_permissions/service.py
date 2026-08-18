"""Permission identities, capability grants, and access checks."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from liteyukibot import AuthorizationContext
from liteyukibot.events import EventEnvelope
from liteyukibot.management import ManagementCaller
from liteyukibot.services import ServiceKey

PUBLIC = "public"
PERMISSION_SERVICE = ServiceKey("liteyukibot.permissions", 2)

type AuthorizationInput = AuthorizationContext | EventEnvelope


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


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    """A redacted, immutable record of one privileged policy decision."""

    capability: str
    principal: Principal | None
    component: str
    event_id: str
    allowed: bool
    reason: str


def authorization_context(value: AuthorizationInput) -> AuthorizationContext:
    """Convert legacy event callers without retaining event payload data."""

    if isinstance(value, AuthorizationContext):
        return value
    return AuthorizationContext(
        event_id=value.id,
        runtime_id=value.runtime_id,
        bot_id=value.bot_id,
        actor_id=None if value.actor is None else value.actor.id,
    )


class PermissionService(Protocol):
    def principal(self, event: EventEnvelope) -> Principal | None: ...

    def resolve(self, event: EventEnvelope) -> PermissionSnapshot: ...

    def allows(self, event: EventEnvelope, capability: str) -> bool: ...


class PermissionV2Service(Protocol):
    """Host-facing v2 authorization surface with no EventEnvelope payload."""

    def resolve(self, context: AuthorizationContext) -> PermissionSnapshot: ...

    def allows(self, context: AuthorizationContext, capability: str) -> bool: ...

    def activation_allowed(self, extension_id: str, capabilities: frozenset[str]) -> bool: ...

    def allows_extension(
        self,
        context: AuthorizationContext,
        extension_id: str,
        capability: str,
        *,
        full: bool,
    ) -> bool: ...


class ManagementPermissionService(Protocol):
    def allows_management(self, caller: ManagementCaller, capability: str) -> bool: ...


class PermissionAuditService(PermissionService, Protocol):
    def decide(self, event: EventEnvelope, capability: str, *, component: str) -> bool: ...

    def activation_allowed(self, extension_id: str, capabilities: frozenset[str]) -> bool: ...

    def allows_extension(
        self,
        context: AuthorizationContext,
        extension_id: str,
        capability: str,
        *,
        full: bool,
    ) -> bool: ...

    def audit(self, *, limit: int | None = None) -> tuple[PermissionDecision, ...]: ...


class PermissionLogger(Protocol):
    def bind(self, **fields: object) -> PermissionLogger: ...

    def info(self, message: str, *args: object, **kwargs: object) -> None: ...


class _ConfiguredPermissionService:
    AUDIT_CAPACITY = 256

    def __init__(
        self,
        snapshots: Mapping[Principal, PermissionSnapshot],
        management_grants: Mapping[str, PermissionSnapshot],
        plugin_capabilities: Mapping[str, frozenset[str]],
        *,
        logger: PermissionLogger | None = None,
    ) -> None:
        self._snapshots = dict(snapshots)
        self._management_grants = dict(management_grants)
        self._plugin_capabilities = dict(plugin_capabilities)
        self._anonymous = PermissionSnapshot(None, frozenset(), frozenset({PUBLIC}))
        self._logger = logger
        self._audit: deque[PermissionDecision] = deque(maxlen=self.AUDIT_CAPACITY)

    def principal(self, context: AuthorizationInput) -> Principal | None:
        normalized = authorization_context(context)
        if normalized.actor_id is None:
            return None
        return Principal(
            runtime_id=normalized.runtime_id,
            bot_id=normalized.bot_id,
            actor_id=normalized.actor_id,
        )

    def resolve(self, context: AuthorizationInput) -> PermissionSnapshot:
        principal = self.principal(context)
        if principal is None:
            return self._anonymous
        return self._snapshots.get(
            principal,
            PermissionSnapshot(principal, frozenset(), frozenset({PUBLIC})),
        )

    def allows(self, context: AuthorizationInput, capability: str) -> bool:
        if not isinstance(capability, str):
            return False
        if not capability or capability != capability.strip() or any(character.isspace() for character in capability):
            return False
        return self.resolve(context).allows(capability)

    def allows_management(self, caller: ManagementCaller, capability: str) -> bool:
        if not isinstance(capability, str) or not capability or capability != capability.strip():
            return False
        return self._management_grants.get(caller.id, self._anonymous).allows(capability)

    def decide(self, context: AuthorizationInput, capability: str, *, component: str) -> bool:
        """Evaluate and retain a redacted audit record for a privileged boundary."""

        component = _validate_token("decision component", component)
        normalized = authorization_context(context)
        principal = self.principal(normalized)
        if (
            not isinstance(capability, str)
            or not capability
            or capability != capability.strip()
            or any(character.isspace() for character in capability)
        ):
            allowed = False
            reason = "invalid_capability"
        else:
            allowed = self.resolve(normalized).allows(capability)
            reason = "granted" if allowed else "not_granted"
        decision = PermissionDecision(
            capability=capability if isinstance(capability, str) else repr(capability),
            principal=principal,
            component=component,
            event_id=normalized.event_id,
            allowed=allowed,
            reason=reason,
        )
        self._audit.append(decision)
        if self._logger is not None:
            fields: dict[str, object] = {
                "permission_component": component,
                "capability": decision.capability,
                "event_id": normalized.event_id,
                "allowed": allowed,
                "reason": reason,
            }
            if principal is not None:
                fields.update(
                    runtime=principal.runtime_id,
                    bot_id=principal.bot_id,
                    actor_id=principal.actor_id,
                )
            self._logger.bind(**fields).info("permission decision {}", "granted" if allowed else "denied")
        return allowed

    def activation_allowed(self, extension_id: str, capabilities: frozenset[str]) -> bool:
        """Fail closed unless every Native/downscoped capability is explicitly granted."""

        extension_id = _validate_token("extension id", extension_id)
        requested = frozenset(_validate_token("requested capability", capability) for capability in capabilities)
        ceiling = self._plugin_capabilities.get(extension_id)
        return ceiling is not None and requested <= ceiling

    def allows_extension(
        self,
        context: AuthorizationContext,
        extension_id: str,
        capability: str,
        *,
        full: bool,
    ) -> bool:
        """Authorize one host privilege while retaining only redacted context fields."""

        extension_id = _validate_token("extension id", extension_id)
        allowed = full or (
            self.activation_allowed(extension_id, frozenset({capability})) and self.allows(context, capability)
        )
        decision = PermissionDecision(
            capability=capability,
            principal=self.principal(context),
            component=extension_id,
            event_id=context.event_id,
            allowed=allowed,
            reason="full_host" if full else "granted" if allowed else "not_granted",
        )
        self._audit.append(decision)
        return allowed

    def audit(self, *, limit: int | None = None) -> tuple[PermissionDecision, ...]:
        """Return newest redacted decisions, without exposing message or tool payloads."""

        if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 0):
            raise ValueError("audit limit must be a non-negative integer")
        decisions = tuple(self._audit)
        if limit is None:
            return decisions
        return () if limit == 0 else decisions[-limit:]


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


def _parse_management_grants(value: object, roles: Mapping[str, frozenset[str]]) -> dict[str, PermissionSnapshot]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError("permission management_grants must be a sequence of objects")
    grants: dict[str, PermissionSnapshot] = {}
    for index, raw in enumerate(value):
        location = f"management_grants[{index}]"
        if not isinstance(raw, Mapping) or set(raw) - {"id", "roles", "capabilities"} or "id" not in raw:
            raise ValueError(f"permission {location} must contain id, roles, and/or capabilities")
        caller_id = _validate_token(f"{location}.id", raw["id"])
        if caller_id in grants:
            raise ValueError(f"permission {location} duplicates an earlier management caller")
        assigned_roles = _parse_token_sequence(raw.get("roles", ()), location=f"{location}.roles", kind="role")
        direct = _parse_token_sequence(
            raw.get("capabilities", ()), location=f"{location}.capabilities", kind="capability"
        )
        if not assigned_roles and not direct:
            raise ValueError(f"permission {location} must assign at least one role or capability")
        if PUBLIC in direct:
            raise ValueError(f"permission {location} must not grant reserved capability {PUBLIC}")
        unknown = set(assigned_roles) - roles.keys()
        if unknown:
            raise ValueError(f"permission {location} references unknown roles: {', '.join(sorted(unknown))}")
        capabilities = {PUBLIC, *direct}
        for role in assigned_roles:
            capabilities.update(roles[role])
        grants[caller_id] = PermissionSnapshot(None, frozenset(assigned_roles), frozenset(capabilities))
    return grants


def _parse_plugin_capabilities(value: object) -> dict[str, frozenset[str]]:
    if not isinstance(value, Mapping):
        raise TypeError("permission plugin_capabilities must be an object")
    parsed: dict[str, frozenset[str]] = {}
    for raw_id, raw_capabilities in value.items():
        extension_id = _validate_token("plugin_capabilities extension id", raw_id)
        if extension_id in parsed:
            raise ValueError(f"permission plugin_capabilities duplicates {extension_id}")
        parsed[extension_id] = frozenset(
            _parse_token_sequence(raw_capabilities, location=f"plugin_capabilities.{extension_id}", kind="capability")
        )
    return parsed


def create_permission_service(
    config: Mapping[str, Any], *, logger: PermissionLogger | None = None
) -> PermissionAuditService:
    if not all(isinstance(key, str) for key in config):
        raise TypeError("permission config keys must be strings")
    unknown = set(config) - {"roles", "grants", "management_grants", "plugin_capabilities"}
    if unknown:
        raise ValueError(f"unknown permission config keys: {', '.join(sorted(unknown))}")
    roles = _parse_roles(config.get("roles", {}))
    snapshots = _parse_grants(config.get("grants", ()), roles)
    management_grants = _parse_management_grants(config.get("management_grants", ()), roles)
    plugin_capabilities = _parse_plugin_capabilities(config.get("plugin_capabilities", {}))
    return _ConfiguredPermissionService(snapshots, management_grants, plugin_capabilities, logger=logger)


__all__ = [
    "PERMISSION_SERVICE",
    "PUBLIC",
    "AuthorizationInput",
    "PermissionDecision",
    "PermissionAuditService",
    "PermissionLogger",
    "ManagementPermissionService",
    "PermissionService",
    "PermissionV2Service",
    "PermissionSnapshot",
    "Principal",
    "authorization_context",
]
