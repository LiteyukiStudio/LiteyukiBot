"""Built-in persistent profile feature implemented directly on Cordis."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from liteyukibot_cordis import Scope

from liteyukibot.i18n import I18N_SERVICE

from .common import NullTranslator, optional_use, publish_service
from .profile_service import (
    PROFILE_SERVICE,
    ProfileMigrationRequiredError,
    ProfileService,
    ProfileSnapshot,
    SQLiteProfileService,
    language_value,
    nickname_value,
)
from .resources import RESOURCE_SERVICE
from .resources_models import ResourceField, ResourceSpec
from .resources_service import ResourceService

PROFILE_DATABASE = "liteyukibot.profile.database"


async def activate(scope: Scope) -> None:
    """Create profile storage, register its resource, and publish the service."""
    resources = cast(ResourceService, await scope.use(RESOURCE_SERVICE))
    translator = await optional_use(scope, I18N_SERVICE, NullTranslator())
    raw_database = scope.config.get("database")
    if raw_database is None:
        raw_database = await optional_use(scope, PROFILE_DATABASE, None)
    if raw_database is None:
        raise RuntimeError("profile feature requires a database path")
    if not isinstance(raw_database, (str, Path)):
        raise TypeError("profile database path must be a string or Path")
    database = Path(raw_database)
    database.parent.mkdir(parents=True, exist_ok=True)
    service = SQLiteProfileService(database)
    try:
        registration = resources.register(
            ResourceSpec(
                "profile",
                summary=translator.text("profile.summary", "Manage your user profile"),
                fields=(
                    ResourceField(
                        "nickname",
                        nickname_value,
                        description=translator.text("profile.field.nickname", "Display name; 1 to 32 characters"),
                    ),
                    ResourceField(
                        "language",
                        language_value,
                        description=translator.text("profile.field.language", "Display language: zh-CN or en"),
                    ),
                ),
            ),
            service,
            owner=scope.plugin_id,
        )
    except BaseException:
        await service.close()
        raise

    async def close() -> None:
        resources.unregister(registration)
        await service.close()

    # Own storage before publishing the service so a later registry failure
    # still closes the SQLite connection during activation rollback.
    scope.own(close)
    await publish_service(scope, PROFILE_SERVICE, service)


__all__ = [
    "PROFILE_DATABASE",
    "PROFILE_SERVICE",
    "ProfileMigrationRequiredError",
    "ProfileService",
    "ProfileSnapshot",
    "SQLiteProfileService",
    "activate",
    "language_value",
    "nickname_value",
]
