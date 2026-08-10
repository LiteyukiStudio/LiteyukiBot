"""Native plugin entry point for the permission service."""

from __future__ import annotations

from liteyukibot import PluginContext, PluginDefinition, PluginManifest

from .service import PERMISSION_SERVICE, create_permission_service


async def setup(context: PluginContext) -> None:
    service = create_permission_service(context.config)
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
    )


__all__ = ["create_plugin"]
