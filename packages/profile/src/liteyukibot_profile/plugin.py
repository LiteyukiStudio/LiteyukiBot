"""Native plugin entry point for persistent user profiles."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from liteyukibot_resources import RESOURCE_SERVICE, ResourceField, ResourceService, ResourceSpec

from liteyukibot import (
    AuthorizationContext,
    PluginContext,
    PluginDefinition,
    PluginInitSpec,
    PluginManifest,
    ToolDeclaration,
)
from liteyukibot.i18n import I18N_SERVICE, Translator
from liteyukibot.plugins import JsonValue, ToolCallback
from liteyukibot.resource_packs import ResourcePackDeclaration
from liteyukibot.services import ServiceRequirement

from .service import PROFILE_SERVICE, SQLiteProfileService, language_value, nickname_value


async def setup(context: PluginContext) -> None:
    """Implement the setup operation for the component.

    Args:
        context: Runtime or authorization context for the operation.

    Returns:
        None.
    """
    if any(context.config.get(key) == 1 for key in ("api_version", "schema_version", "version")):
        raise RuntimeError("migration_required")
    if context.paths is None:
        raise RuntimeError("profile plugin requires private storage")
    resources = cast(ResourceService, context.services.require(RESOURCE_SERVICE))
    translator = cast(Translator, context.services.require(I18N_SERVICE))
    service = SQLiteProfileService(context.paths.data / "profile.sqlite3")
    registration = resources.register(
        ResourceSpec(
            "profile",
            summary=translator.text("profile.summary", "Manage your user profile"),
            fields=(
                ResourceField(
                    "nickname",
                    nickname_value,
                    description=translator.text("profile.field.nickname", "Display name; 1 to 32 characters"),
                ),
                ResourceField(
                    "language",
                    language_value,
                    description=translator.text("profile.field.language", "Display language: zh-CN or en"),
                ),
            ),
        ),
        service,
        owner=context.id,
    )
    context.services.provide(PROFILE_SERVICE, service)

    async def inspect_tool(authorization: AuthorizationContext, _arguments: Mapping[str, Any]) -> dict[str, str]:
        """Inspect tool.

        Args:
            authorization: Authenticated authorization context for the request.
            _arguments: The arguments value used by the operation.

        Returns:
            The `dict[str, str]` result produced by the operation.

        Notes:
            Internal implementation detail for `setup.inspect_tool`. It delegates to `get`, `_principal`
            while keeping intermediate state local to the owning operation.
        """
        profile = await service.get(_principal(authorization))
        return {"nickname": profile.nickname, "language": profile.language}

    async def set_tool(authorization: AuthorizationContext, arguments: Mapping[str, Any]) -> dict[str, bool]:
        """Set tool.

        Args:
            authorization: Authenticated authorization context for the request.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `dict[str, bool]` result produced by the operation.

        Notes:
            Internal implementation detail for `setup.set_tool`. It delegates to `_field`, `_value`, `get`,
            `_principal` while keeping intermediate state local to the owning operation.
        """
        field = _field(arguments)
        value = _value(arguments)
        resource_field = _PROFILE_FIELDS.get(field)
        if resource_field is None:
            raise ValueError("unsupported profile Tool field")
        await service.set(_principal(authorization), resource_field, resource_field.converter(value))
        return {"updated": True}

    async def delete_tool(authorization: AuthorizationContext, arguments: Mapping[str, Any]) -> dict[str, bool]:
        """Delete tool.

        Args:
            authorization: Authenticated authorization context for the request.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `dict[str, bool]` result produced by the operation.

        Notes:
            Internal implementation detail for `setup.delete_tool`. It delegates to `_field`, `get`,
            `delete`, `_principal` while keeping intermediate state local to the owning operation.
        """
        field = _field(arguments)
        resource_field = _PROFILE_FIELDS.get(field)
        if resource_field is None:
            raise ValueError("unsupported profile Tool field")
        await service.delete(_principal(authorization), resource_field)
        return {"deleted": True}

    context.register_tool("liteyukibot.profile.inspect", cast(ToolCallback, inspect_tool))
    context.register_tool("liteyukibot.profile.set", cast(ToolCallback, set_tool))
    context.register_tool("liteyukibot.profile.delete", cast(ToolCallback, delete_tool))

    async def close() -> None:
        """Close the setup and release its owned resources.

        Returns:
            None.

        Notes:
            Internal implementation detail for `setup.close`. It delegates to `unregister`, `close` while
            keeping intermediate state local to the owning operation.
        """
        resources.unregister(registration)
        await service.close()

    context.defer_cleanup(close)


def create_plugin(version: str) -> PluginDefinition:
    """Create plugin.

    Args:
        version: The version value used by the operation.

    Returns:
        The `PluginDefinition` result produced by the operation.
    """
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.profile",
            name="LiteyukiBot Profile",
            version=version,
            resource_packs=(ResourcePackDeclaration("liteyukibot_profile"),),
            provides=(PROFILE_SERVICE,),
            requires=(ServiceRequirement(RESOURCE_SERVICE), ServiceRequirement(I18N_SERVICE)),
            storage="private",
            tools=(
                ToolDeclaration(
                    id="liteyukibot.profile.inspect",
                    description="Inspect the current caller's persistent profile.",
                    input_schema=cast(Mapping[str, JsonValue], {"type": "object", "additionalProperties": False}),
                    output_schema=cast(Mapping[str, JsonValue], {
                        "type": "object",
                        "properties": {
                            "nickname": {"type": "string"},
                            "language": {"enum": ["zh-CN", "en"]},
                        },
                        "required": ["nickname", "language"],
                        "additionalProperties": False,
                    }),
                ),
                ToolDeclaration(
                    id="liteyukibot.profile.set",
                    description="Set one field on the current caller's persistent profile.",
                    input_schema=cast(Mapping[str, JsonValue], _SET_SCHEMA),
                    output_schema=cast(Mapping[str, JsonValue], _UPDATED_SCHEMA),
                ),
                ToolDeclaration(
                    id="liteyukibot.profile.delete",
                    description="Reset one field on the current caller's persistent profile.",
                    input_schema=cast(Mapping[str, JsonValue], _FIELD_SCHEMA),
                    output_schema=cast(Mapping[str, JsonValue], _DELETED_SCHEMA),
                ),
            ),
        ),
        setup=setup,
        init_spec=PluginInitSpec(description="Private per-user profile storage and resource fields."),
    )


__all__ = ["PROFILE_SERVICE", "create_plugin"]


_PROFILE_FIELDS = {
    "nickname": ResourceField("nickname", nickname_value),
    "language": ResourceField("language", language_value),
}
_FIELD_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"field": {"enum": ["nickname", "language"]}},
    "required": ["field"],
    "additionalProperties": False,
}
_SET_SCHEMA: dict[str, object] = {
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "field": {"const": "nickname"},
                "value": {"type": "string", "minLength": 1, "maxLength": 32, "pattern": r".*\S.*"},
            },
            "required": ["field", "value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "field": {"const": "language"},
                "value": {"enum": ["zh-CN", "en"]},
            },
            "required": ["field", "value"],
            "additionalProperties": False,
        },
    ],
}
_UPDATED_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"updated": {"const": True}},
    "required": ["updated"],
    "additionalProperties": False,
}
_DELETED_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"deleted": {"const": True}},
    "required": ["deleted"],
    "additionalProperties": False,
}


def _principal(context: AuthorizationContext) -> Any:
    """Implement the principal operation for the component.

    Args:
        context: Runtime or authorization context for the operation.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_principal`. It performs the local state transition directly
        and is not a stable extension boundary.
    """
    if context.actor_id is None:
        raise ValueError("profile Tools require an actor")
    from liteyukibot_permissions import Principal

    return Principal(context.runtime_id, context.bot_id, context.actor_id)


def _field(arguments: Mapping[str, Any]) -> str:
    """Implement the field operation for the component.

    Args:
        arguments: JSON-safe arguments supplied to the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_field`. It delegates to `get`, `cast` while keeping
        intermediate state local to the owning operation.
    """
    field = arguments.get("field")
    if field not in _PROFILE_FIELDS:
        raise ValueError("unsupported profile Tool field")
    return cast(str, field)


def _value(arguments: Mapping[str, Any]) -> str:
    """Implement the value operation for the component.

    Args:
        arguments: JSON-safe arguments supplied to the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_value`. It delegates to `get` while keeping intermediate
        state local to the owning operation.
    """
    value = arguments.get("value")
    if not isinstance(value, str):
        raise ValueError("invalid profile Tool value")
    return value
