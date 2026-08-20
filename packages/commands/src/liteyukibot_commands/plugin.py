"""Native plugin entry point for command routing."""

from __future__ import annotations

from typing import cast

from liteyukibot_permissions import PERMISSION_SERVICE, PermissionService

from liteyukibot import (
    InitFieldKind,
    InitFieldSpec,
    PluginContext,
    PluginDefinition,
    PluginInitSpec,
    PluginManifest,
    ResourcePackDeclaration,
)
from liteyukibot.agents import AGENT_HISTORY_SERVICE, AgentHistoryService
from liteyukibot.capabilities import AGENT_HISTORY_CLEAR
from liteyukibot.events import HandlerResult
from liteyukibot.i18n import I18N_SERVICE, Translator
from liteyukibot.services import ServiceRequirement

from .models import CommandInvocation, CommandSpec
from .service import COMMAND_SERVICE, create_command_service


async def setup(context: PluginContext) -> None:
    if any(context.config.get(key) == 1 for key in ("api_version", "schema_version", "version")):
        raise RuntimeError("migration_required")
    permissions = cast(PermissionService, context.services.require(PERMISSION_SERVICE))
    service = create_command_service(context.config, permissions, context.logger)
    context.services.provide(COMMAND_SERVICE, service)
    subscription = context.events.subscribe(
        service.dispatch,
        order=-100,
        name="liteyukibot.commands",
    )

    context.defer_cleanup(lambda: context.events.unsubscribe(subscription))

    history = context.services.get_optional(AGENT_HISTORY_SERVICE)
    translator = context.services.get_optional(I18N_SERVICE)
    if isinstance(history, AgentHistoryService) and isinstance(translator, Translator):

        async def forget(invocation: CommandInvocation) -> HandlerResult:
            try:
                cleared = await history.clear(invocation.event)
            except PermissionError:
                return invocation.reply(
                    translator.text(
                        "agent.command.forget.denied",
                        "You are not allowed to clear this Agent history.",
                    )
                )
            except (ConnectionError, RuntimeError, TimeoutError):
                return invocation.reply(
                    translator.text(
                        "agent.command.forget.unavailable",
                        "The Agent history service is unavailable.",
                    )
                )
            return invocation.reply(
                translator.text(
                    "agent.command.forget.complete",
                    "Cleared {count} saved Agent message(s).",
                    count=cleared,
                )
            )

        service.register(
            CommandSpec(
                "forget",
                path=("agent",),
                summary=translator.text(
                    "agent.command.forget.summary",
                    "Clear your Agent conversation history",
                ),
                permission=AGENT_HISTORY_CLEAR,
            ),
            forget,
            owner=context.id,
        )
        context.defer_cleanup(lambda: service.unregister_owner(context.id))


def create_plugin(version: str) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.commands",
            name="LiteyukiBot Commands",
            version=version,
            resource_packs=(ResourcePackDeclaration("liteyukibot_commands"),),
            provides=(COMMAND_SERVICE,),
            requires=(
                ServiceRequirement(PERMISSION_SERVICE),
                ServiceRequirement(AGENT_HISTORY_SERVICE, optional=True),
                ServiceRequirement(I18N_SERVICE, optional=True),
            ),
        ),
        setup=setup,
        init_spec=PluginInitSpec(
            description="Protocol-neutral command routing.",
            fields=(
                InitFieldSpec(
                    key="prefixes",
                    label="Command prefixes",
                    label_key="commands.init.prefixes",
                    kind=InitFieldKind.STRING_LIST,
                    default=("/",),
                ),
            ),
        ),
    )


__all__ = ["create_plugin"]
