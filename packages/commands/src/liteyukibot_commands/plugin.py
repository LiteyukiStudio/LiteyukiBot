"""Native plugin entry point for command routing."""

from __future__ import annotations

from typing import cast

from liteyukibot_permissions import PERMISSION_SERVICE, PermissionService

from liteyukibot import (
    InitFieldKind,
    InitFieldSpec,
    PluginContext,
    PluginDefinition,
    PluginInitSpec,
    PluginManifest,
    ResourcePackDeclaration,
)
from liteyukibot.services import ServiceRequirement

from .service import COMMAND_SERVICE, create_command_service


async def setup(context: PluginContext) -> None:
    if any(context.config.get(key) == 1 for key in ("api_version", "schema_version", "version")):
        raise RuntimeError("migration_required")
    permissions = cast(PermissionService, context.services.require(PERMISSION_SERVICE))
    service = create_command_service(context.config, permissions, context.logger)
    context.services.provide(COMMAND_SERVICE, service)
    subscription = context.events.subscribe(
        service.dispatch,
        order=-100,
        name="liteyukibot.commands",
    )

    context.defer_cleanup(lambda: context.events.unsubscribe(subscription))


def create_plugin(version: str) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.commands",
            name="LiteyukiBot Commands",
            version=version,
            resource_packs=(ResourcePackDeclaration("liteyukibot_commands"),),
            provides=(COMMAND_SERVICE,),
            requires=(ServiceRequirement(PERMISSION_SERVICE),),
        ),
        setup=setup,
        init_spec=PluginInitSpec(
            description="Protocol-neutral command routing.",
            fields=(
                InitFieldSpec(
                    key="prefixes",
                    label="Command prefixes",
                    label_key="commands.init.prefixes",
                    kind=InitFieldKind.STRING_LIST,
                    default=("/",),
                ),
            ),
        ),
    )


__all__ = ["create_plugin"]
