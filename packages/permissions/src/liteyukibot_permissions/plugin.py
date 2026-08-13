"""Native plugin entry point for the permission service."""

from __future__ import annotations

from liteyukibot import PluginContext, PluginDefinition, PluginInitSpec, PluginManifest

from .service import PERMISSION_SERVICE, create_permission_service


async def setup(context: PluginContext) -> None:
    service = create_permission_service(context.config, logger=context.logger)
    context.services.provide(PERMISSION_SERVICE, service)


def create_plugin(version: str) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.permissions",
            name="LiteyukiBot Permissions",
            version=version,
            provides=(PERMISSION_SERVICE,),
        ),
        setup=setup,
        init_spec=PluginInitSpec(description="Permission grants and roles can be configured after initialization."),
    )


__all__ = ["create_plugin"]
