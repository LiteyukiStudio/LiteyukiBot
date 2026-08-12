"""Native plugin entry point for the resource registry."""

from __future__ import annotations

from typing import cast

from liteyukibot_commands import COMMAND_SERVICE, CommandService
from liteyukibot_permissions import PERMISSION_SERVICE, PermissionService

from liteyukibot import PluginContext, PluginDefinition, PluginHandle, PluginInitSpec, PluginManifest
from liteyukibot.i18n import I18N_SERVICE, Translator
from liteyukibot.resource_packs import ResourcePackDeclaration
from liteyukibot.services import ServiceRequirement

from .service import RESOURCE_SERVICE, create_resource_service


async def setup(context: PluginContext) -> PluginHandle:
    permissions = cast(PermissionService, context.services.require(PERMISSION_SERVICE))
    commands = cast(CommandService, context.services.require(COMMAND_SERVICE))
    translator = cast(Translator, context.services.require(I18N_SERVICE))
    context.services.provide(RESOURCE_SERVICE, create_resource_service(permissions, commands, translator))
    return PluginHandle()


def create_plugin(version: str) -> PluginDefinition:
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
        ),
        setup=setup,
        init_spec=PluginInitSpec(description="Resource registry required by persistent profile plugins."),
    )


__all__ = ["create_plugin"]
