"""Native plugin entry point for the resource registry."""

from __future__ import annotations

from typing import cast

from liteyukibot_permissions import PERMISSION_SERVICE, PermissionService

from liteyukibot import PluginContext, PluginDefinition, PluginHandle, PluginManifest
from liteyukibot.services import ServiceRequirement

from .service import RESOURCE_SERVICE, create_resource_service


async def setup(context: PluginContext) -> PluginHandle:
    permissions = cast(PermissionService, context.services.require(PERMISSION_SERVICE))
    context.services.provide(RESOURCE_SERVICE, create_resource_service(permissions))
    return PluginHandle()


def create_plugin(version: str) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.resources",
            name="LiteyukiBot Resources",
            version=version,
            provides=(RESOURCE_SERVICE,),
            requires=(ServiceRequirement(PERMISSION_SERVICE),),
        ),
        setup=setup,
    )


__all__ = ["create_plugin"]
