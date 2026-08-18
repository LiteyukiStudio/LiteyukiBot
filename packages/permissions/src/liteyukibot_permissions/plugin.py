"""Native plugin entry point for the permission service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from liteyukibot import (
    AuthorizationContext,
    PluginContext,
    PluginDefinition,
    PluginInitSpec,
    PluginManifest,
    ToolDeclaration,
)
from liteyukibot.plugins import ToolCallback

from .service import PERMISSION_SERVICE, PermissionV2Service, create_permission_service


async def setup(context: PluginContext) -> None:
    _reject_legacy_config(context.config)
    service = create_permission_service(context.config, logger=context.logger)
    context.services.provide(PERMISSION_SERVICE, service)

    async def check_tool(authorization: AuthorizationContext, arguments: Mapping[str, Any]) -> dict[str, bool]:
        capability = arguments.get("capability")
        if not isinstance(capability, str) or not capability:
            raise ValueError("permission capability must be a non-empty string")
        return {"allowed": cast(PermissionV2Service, service).allows(authorization, capability)}

    context.register_tool("liteyukibot.permissions.check", cast(ToolCallback, check_tool))


def create_plugin(version: str) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.permissions",
            name="LiteyukiBot Permissions",
            version=version,
            provides=(PERMISSION_SERVICE,),
            tools=(
                ToolDeclaration(
                    id="liteyukibot.permissions.check",
                    description="Check one capability for the current invocation context.",
                    input_schema={
                        "type": "object",
                        "properties": {"capability": {"type": "string", "minLength": 1}},
                        "required": ["capability"],
                        "additionalProperties": False,
                    },
                    output_schema={
                        "type": "object",
                        "properties": {"allowed": {"type": "boolean"}},
                        "required": ["allowed"],
                        "additionalProperties": False,
                    },
                ),
            ),
        ),
        setup=setup,
        init_spec=PluginInitSpec(description="Permission grants and roles can be configured after initialization."),
    )


__all__ = ["create_plugin"]


def _reject_legacy_config(config: Mapping[str, Any]) -> None:
    if any(config.get(key) == 1 for key in ("api_version", "schema_version", "version")):
        raise RuntimeError("migration_required")
