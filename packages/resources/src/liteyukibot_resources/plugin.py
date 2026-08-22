"""Native plugin entry point for the resource registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from liteyukibot_commands import COMMAND_SERVICE, CommandService
from liteyukibot_permissions import PERMISSION_SERVICE, PermissionService

from liteyukibot import (
    AuthorizationContext,
    PluginContext,
    PluginDefinition,
    PluginHandle,
    PluginInitSpec,
    PluginManifest,
    ToolDeclaration,
)
from liteyukibot.i18n import I18N_SERVICE, Translator
from liteyukibot.plugins import JsonValue, ToolCallback
from liteyukibot.resource_packs import ResourcePackDeclaration
from liteyukibot.services import ServiceRequirement

from .service import RESOURCE_SERVICE, create_resource_service


async def setup(context: PluginContext) -> PluginHandle:
    """Implement the setup operation for the component.

    Args:
        context: Runtime or authorization context for the operation.

    Returns:
        The `PluginHandle` result produced by the operation.
    """
    if any(context.config.get(key) == 1 for key in ("api_version", "schema_version", "version")):
        raise RuntimeError("migration_required")
    permissions = cast(PermissionService, context.services.require(PERMISSION_SERVICE))
    commands = cast(CommandService, context.services.require(COMMAND_SERVICE))
    translator = cast(Translator, context.services.require(I18N_SERVICE))
    service = create_resource_service(permissions, commands, translator)
    context.services.provide(RESOURCE_SERVICE, service)

    async def inspect_tool(
        authorization: AuthorizationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, object]:
        """Inspect tool.

        Args:
            authorization: Authenticated authorization context for the request.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.

        Notes:
            Internal implementation detail for `setup.inspect_tool`. It delegates to `inspect_context`,
            `_path` while keeping intermediate state local to the owning operation.
        """
        return dict(await service.inspect_context(authorization, _path(arguments)))

    async def set_tool(authorization: AuthorizationContext, arguments: Mapping[str, Any]) -> dict[str, object]:
        """Set tool.

        Args:
            authorization: Authenticated authorization context for the request.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.

        Notes:
            Internal implementation detail for `setup.set_tool`. It delegates to `set_context`, `_path`,
            `_field`, `_value` while keeping intermediate state local to the owning operation.
        """
        await service.set_context(authorization, _path(arguments), _field(arguments), _value(arguments))
        return {"updated": True}

    async def delete_tool(authorization: AuthorizationContext, arguments: Mapping[str, Any]) -> dict[str, object]:
        """Delete tool.

        Args:
            authorization: Authenticated authorization context for the request.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `dict[str, object]` result produced by the operation.

        Notes:
            Internal implementation detail for `setup.delete_tool`. It delegates to `delete_context`,
            `_path`, `_field` while keeping intermediate state local to the owning operation.
        """
        await service.delete_context(authorization, _path(arguments), _field(arguments))
        return {"deleted": True}

    context.register_tool("liteyukibot.resources.inspect", cast(ToolCallback, inspect_tool))
    context.register_tool("liteyukibot.resources.set", cast(ToolCallback, set_tool))
    context.register_tool("liteyukibot.resources.delete", cast(ToolCallback, delete_tool))
    return PluginHandle()


def create_plugin(version: str) -> PluginDefinition:
    """Create plugin.

    Args:
        version: The version value used by the operation.

    Returns:
        The `PluginDefinition` result produced by the operation.
    """
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.resources",
            name="LiteyukiBot Resources",
            version=version,
            resource_packs=(ResourcePackDeclaration("liteyukibot_resources"),),
            provides=(RESOURCE_SERVICE,),
            requires=(
                ServiceRequirement(PERMISSION_SERVICE),
                ServiceRequirement(COMMAND_SERVICE),
                ServiceRequirement(I18N_SERVICE),
            ),
            tools=(
                ToolDeclaration(
                    id="liteyukibot.resources.inspect",
                    description="Inspect the current caller's structured resource values.",
                    input_schema=cast(Mapping[str, JsonValue], _INSPECT_SCHEMA),
                    output_schema=cast(Mapping[str, JsonValue], _INSPECT_OUTPUT_SCHEMA),
                ),
                ToolDeclaration(
                    id="liteyukibot.resources.set",
                    description="Set one structured resource field for the current caller.",
                    input_schema=cast(Mapping[str, JsonValue], _SET_SCHEMA),
                    output_schema={
                        "type": "object",
                        "properties": {"updated": {"const": True}},
                        "required": ["updated"],
                        "additionalProperties": False,
                    },
                ),
                ToolDeclaration(
                    id="liteyukibot.resources.delete",
                    description="Reset one structured resource field for the current caller.",
                    input_schema=cast(Mapping[str, JsonValue], _DELETE_SCHEMA),
                    output_schema={
                        "type": "object",
                        "properties": {"deleted": {"const": True}},
                        "required": ["deleted"],
                        "additionalProperties": False,
                    },
                ),
            ),
        ),
        setup=setup,
        init_spec=PluginInitSpec(description="Resource registry required by persistent profile plugins."),
    )


__all__ = ["create_plugin"]


_PATH_SCHEMA: dict[str, object] = {
    "type": "array",
    "items": {"type": "string", "minLength": 1},
    "minItems": 1,
}
_INSPECT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"path": _PATH_SCHEMA},
    "required": ["path"],
    "additionalProperties": False,
}
_DELETE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"path": _PATH_SCHEMA, "field": {"type": "string", "minLength": 1}},
    "required": ["path", "field"],
    "additionalProperties": False,
}
_SET_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "path": _PATH_SCHEMA,
        "field": {"type": "string", "minLength": 1},
        "value": {"type": "string"},
    },
    "required": ["path", "field", "value"],
    "additionalProperties": False,
}
_INSPECT_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": {"$ref": "#/$defs/jsonValue"},
    "$defs": {
        "jsonValue": {
            "anyOf": [
                {"type": "null"},
                {"type": "boolean"},
                {"type": "number"},
                {"type": "string"},
                {"type": "array", "items": {"$ref": "#/$defs/jsonValue"}},
                {
                    "type": "object",
                    "additionalProperties": {"$ref": "#/$defs/jsonValue"},
                },
            ]
        }
    },
}


def _path(arguments: Mapping[str, Any]) -> tuple[str, ...]:
    """Implement the path operation for the component.

    Args:
        arguments: JSON-safe arguments supplied to the operation.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_path`. It delegates to `get`, `all` while keeping
        intermediate state local to the owning operation.
    """
    path = arguments.get("path")
    if not isinstance(path, list) or not path or not all(isinstance(part, str) and part for part in path):
        raise ValueError("invalid resource Tool path")
    return tuple(path)


def _field(arguments: Mapping[str, Any]) -> str:
    """Implement the field operation for the component.

    Args:
        arguments: JSON-safe arguments supplied to the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_field`. It delegates to `get` while keeping intermediate
        state local to the owning operation.
    """
    field = arguments.get("field")
    if not isinstance(field, str) or not field:
        raise ValueError("invalid resource Tool field")
    return field


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
        raise ValueError("invalid resource Tool value")
    return value
