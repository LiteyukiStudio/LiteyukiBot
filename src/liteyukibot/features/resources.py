"""Built-in structured-resource feature implemented directly on Cordis."""

from __future__ import annotations

from typing import cast

from liteyukibot_cordis import Scope

from liteyukibot.i18n import I18N_SERVICE

from .commands import COMMAND_SERVICE, CommandService
from .common import NullTranslator, optional_use, publish_service
from .permissions import PERMISSION_SERVICE, PermissionService
from .resources_models import (
    ResourceConverter,
    ResourceField,
    ResourceOperation,
    ResourceProvider,
    ResourceRegistration,
    ResourceSpec,
)
from .resources_service import RESOURCE_SERVICE, ResourceError, ResourceService, create_resource_service


async def activate(scope: Scope) -> None:
    """Provide resource registration and operation dispatch."""
    permissions = cast(PermissionService, await scope.use(PERMISSION_SERVICE))
    commands = cast(CommandService, await scope.use(COMMAND_SERVICE))
    translator = await optional_use(scope, I18N_SERVICE, NullTranslator())
    service = create_resource_service(permissions, commands, translator)
    await publish_service(scope, RESOURCE_SERVICE, service)


__all__ = [
    "ResourceConverter",
    "ResourceError",
    "ResourceField",
    "ResourceOperation",
    "ResourceProvider",
    "ResourceRegistration",
    "ResourceService",
    "ResourceSpec",
    "RESOURCE_SERVICE",
    "activate",
    "create_resource_service",
]
