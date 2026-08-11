"""Native plugin entry point for persistent user profiles."""

from __future__ import annotations

from typing import cast

from liteyukibot_resources import RESOURCE_SERVICE, ResourceField, ResourceService, ResourceSpec

from liteyukibot import PluginContext, PluginDefinition, PluginInitSpec, PluginManifest
from liteyukibot.services import ServiceRequirement

from .service import PROFILE_SERVICE, SQLiteProfileService, language_value, nickname_value


async def setup(context: PluginContext) -> None:
    if context.paths is None:
        raise RuntimeError("profile plugin requires private storage")
    resources = cast(ResourceService, context.services.require(RESOURCE_SERVICE))
    service = SQLiteProfileService(context.paths.data / "profile.sqlite3")
    registration = resources.register(
        ResourceSpec(
            "profile",
            summary="Manage your user profile",
            fields=(
                ResourceField(
                    "nickname",
                    nickname_value,
                    description="Display name; 1 to 32 characters",
                ),
                ResourceField(
                    "language",
                    language_value,
                    description="Display language: zh-CN or en",
                ),
            ),
        ),
        service,
        owner=context.id,
    )
    context.services.provide(PROFILE_SERVICE, service)

    async def close() -> None:
        resources.unregister(registration)
        await service.close()

    context.defer_cleanup(close)


def create_plugin(version: str) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.profile",
            name="LiteyukiBot Profile",
            version=version,
            provides=(PROFILE_SERVICE,),
            requires=(ServiceRequirement(RESOURCE_SERVICE),),
            storage="private",
        ),
        setup=setup,
        init_spec=PluginInitSpec(description="Private per-user profile storage and resource fields."),
    )


__all__ = ["PROFILE_SERVICE", "create_plugin"]
