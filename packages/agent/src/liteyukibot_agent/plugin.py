"""Native plugin that provides the kernel-side common agent tool broker."""

from __future__ import annotations

from typing import cast

from liteyukibot_commands import COMMAND_SERVICE, CommandInvocation, CommandService, CommandSpec

from liteyukibot import PluginContext, PluginDefinition, PluginInitSpec, PluginManifest, ResourcePackDeclaration
from liteyukibot.agents import AGENT_HISTORY_SERVICE, AGENT_TOOL_BROKER_SERVICE, AgentHistoryService
from liteyukibot.capabilities import AGENT_HISTORY_CLEAR
from liteyukibot.events import HandlerResult
from liteyukibot.i18n import I18N_SERVICE, Translator
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
    commands = context.services.get_optional(COMMAND_SERVICE)
    history = context.services.get_optional(AGENT_HISTORY_SERVICE)
    translator = context.services.get_optional(I18N_SERVICE)
    if commands is None or not isinstance(history, AgentHistoryService) or not isinstance(translator, Translator):
        return
    command_service = cast(CommandService, commands)

    async def forget(invocation: CommandInvocation) -> HandlerResult:
        try:
            cleared = await history.clear(invocation.event)
        except PermissionError:
            return invocation.reply(translator.text("agent.command.forget.denied"))
        except (ConnectionError, RuntimeError, TimeoutError):
            return invocation.reply(translator.text("agent.command.forget.unavailable"))
        return invocation.reply(translator.text("agent.command.forget.complete", count=cleared))

    command_service.register(
        CommandSpec(
            "forget",
            path=("agent",),
            summary=translator.text("agent.command.forget.summary"),
            permission=AGENT_HISTORY_CLEAR,
        ),
        forget,
        owner=context.id,
    )
    context.defer_cleanup(lambda: command_service.unregister_owner(context.id))


def create_plugin(version: str) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.agent",
            name="LiteyukiBot Native Agent",
            version=version,
            resource_packs=(ResourcePackDeclaration("liteyukibot_agent"),),
            provides=(AGENT_TOOL_BROKER_SERVICE,),
            requires=(
                ServiceRequirement(PERMISSION_SERVICE, optional=True),
                ServiceRequirement(COMMAND_SERVICE, optional=True),
                ServiceRequirement(AGENT_HISTORY_SERVICE, optional=True),
                ServiceRequirement(I18N_SERVICE, optional=True),
            ),
        ),
        setup=setup,
        init_spec=PluginInitSpec(description="Kernel-side agent tool broker."),
    )
