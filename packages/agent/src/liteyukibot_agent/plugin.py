"""Native plugin that provides the kernel-side common agent tool broker."""

from __future__ import annotations

from liteyukibot import PluginContext, PluginDefinition, PluginInitSpec, PluginManifest, ResourcePackDeclaration
from liteyukibot.agents import AGENT_TOOL_BROKER_SERVICE
from liteyukibot.services import ServiceKey, ServiceRequirement

from .broker import ToolBroker, permission_checker

PERMISSION_SERVICE = ServiceKey("liteyukibot.permissions", 1)


async def setup(context: PluginContext) -> None:
    if context.config:
        raise ValueError("native agent plugin does not accept plugin configuration")
    permissions = permission_checker(context.services.get_optional(PERMISSION_SERVICE))
    context.services.provide(
        AGENT_TOOL_BROKER_SERVICE,
        ToolBroker.discover(permissions),
    )


def create_plugin(version: str) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.agent",
            name="LiteyukiBot Native Agent",
            version=version,
            resource_packs=(ResourcePackDeclaration("liteyukibot_agent"),),
            provides=(AGENT_TOOL_BROKER_SERVICE,),
            requires=(ServiceRequirement(PERMISSION_SERVICE, optional=True),),
        ),
        setup=setup,
        init_spec=PluginInitSpec(description="Kernel-side agent tool broker."),
    )
