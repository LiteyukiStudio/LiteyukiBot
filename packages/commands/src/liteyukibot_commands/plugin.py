"""Native plugin entry point for command routing."""

from __future__ import annotations

from typing import cast

from liteyukibot_permissions import PERMISSION_SERVICE, PermissionService

from liteyukibot import PluginContext, PluginDefinition, PluginHandle, PluginManifest
from liteyukibot.services import ServiceRequirement

from .service import COMMAND_SERVICE, create_command_service


async def setup(context: PluginContext) -> PluginHandle:
    permissions = cast(PermissionService, context.services.require(PERMISSION_SERVICE))
    service = create_command_service(context.config, permissions, context.logger)
    context.services.provide(COMMAND_SERVICE, service)
    subscription = context.events.subscribe(
        service.dispatch,
        order=-100,
        name="liteyukibot.commands",
    )

    async def stop() -> None:
        context.events.unsubscribe(subscription)

    return PluginHandle(stop=stop)


def create_plugin(version: str) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.commands",
            name="LiteyukiBot Commands",
            version=version,
            provides=(COMMAND_SERVICE,),
            requires=(ServiceRequirement(PERMISSION_SERVICE),),
        ),
        setup=setup,
    )


__all__ = ["create_plugin"]
