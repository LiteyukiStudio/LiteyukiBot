"""Built-in command routing feature implemented directly on Cordis."""

from __future__ import annotations

from typing import cast

from liteyukibot_cordis import Scope

from .commands_models import CommandBinding, CommandHandler, CommandInvocation, CommandRegistration, CommandSpec
from .commands_parsing import (
    ArgumentSpec,
    CommandParseError,
    CommandSchema,
    OptionSpec,
    ParsedCommand,
    ValueConverter,
    boolean_value,
    float_value,
    integer_value,
    parse_command,
    string_value,
    tokenize_command,
)
from .commands_service import COMMAND_SERVICE, CommandService, create_command_service
from .common import LOGGER_PROVIDER, NullLogger, optional_use, publish_service
from .permissions import PERMISSION_SERVICE, PermissionService


async def activate(scope: Scope) -> None:
    """Provide command routing and attach its ordered event handler."""
    permissions = cast(PermissionService, await scope.use(PERMISSION_SERVICE))
    logger = await optional_use(scope, LOGGER_PROVIDER, NullLogger())
    service = create_command_service(scope.config, permissions, logger)
    await publish_service(scope, COMMAND_SERVICE, service)

    async def dispatch(session: object) -> None:
        # Keep the command service independent from Cordis while preserving its
        # HandlerResult/action contract at this boundary.
        cordis_session = session
        event = cordis_session.event.envelope  # type: ignore[attr-defined]
        result = await service.dispatch(event)
        if result is not None:
            for action in result.actions:
                cordis_session.emit(action)  # type: ignore[attr-defined]

    scope.on(dispatch, order=-100)


__all__ = [
    "ArgumentSpec",
    "CommandBinding",
    "CommandHandler",
    "CommandInvocation",
    "CommandParseError",
    "CommandRegistration",
    "CommandSchema",
    "CommandService",
    "CommandSpec",
    "COMMAND_SERVICE",
    "OptionSpec",
    "ParsedCommand",
    "ValueConverter",
    "activate",
    "boolean_value",
    "create_command_service",
    "float_value",
    "integer_value",
    "parse_command",
    "string_value",
    "tokenize_command",
]
