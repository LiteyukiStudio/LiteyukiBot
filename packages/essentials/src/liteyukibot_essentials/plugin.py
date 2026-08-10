"""Native plugin entry point for essential commands."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from liteyukibot_commands import (
    COMMAND_SERVICE,
    CommandBinding,
    CommandInvocation,
    CommandService,
    CommandSpec,
)

from liteyukibot import PluginContext, PluginDefinition, PluginHandle, PluginManifest
from liteyukibot.events import HandlerResult
from liteyukibot.services import ServiceRequirement
from liteyukibot.status import KERNEL_STATUS_SERVICE, KernelStatusProvider

from .render import Language, messages, render_help, render_status

_PUBLIC_PERMISSION = "public"
_OPERATOR_PERMISSION = "operator"


def _language(config: Mapping[str, Any]) -> Language:
    unknown = set(config) - {"language"}
    if unknown:
        raise ValueError(f"unknown essentials config keys: {', '.join(sorted(unknown))}")
    value = config.get("language", "zh-CN")
    if not isinstance(value, str) or value not in {"zh-CN", "en"}:
        raise ValueError("essentials language must be 'zh-CN' or 'en'")
    return cast(Language, value)


async def setup(context: PluginContext) -> PluginHandle:
    language = _language(context.config)
    command_service = cast(CommandService, context.services.require(COMMAND_SERVICE))
    status_provider = cast(KernelStatusProvider, context.services.require(KERNEL_STATUS_SERVICE))
    text = messages(language)

    def help_command(invocation: CommandInvocation) -> HandlerResult:
        visible = command_service.visible(invocation.event)
        return invocation.reply(render_help(visible, prefix=invocation.prefix, language=language))

    def status_command(invocation: CommandInvocation) -> HandlerResult:
        return invocation.reply(render_status(status_provider.snapshot(), language=language))

    bindings: tuple[CommandBinding, ...] = (
        (
            CommandSpec(
                "help",
                aliases=("帮助",),
                summary=text.help_summary,
                permission=_PUBLIC_PERMISSION,
            ),
            help_command,
        ),
        (
            CommandSpec(
                "status",
                aliases=("状态",),
                summary=text.status_summary,
                permission=_OPERATOR_PERMISSION,
            ),
            status_command,
        ),
    )
    registrations = command_service.register_many(bindings, owner=context.id)

    async def stop() -> None:
        for registration in reversed(registrations):
            command_service.unregister(registration)

    return PluginHandle(stop=stop)


def create_plugin(version: str) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.essentials",
            name="LiteyukiBot Essentials",
            version=version,
            requires=(
                ServiceRequirement(COMMAND_SERVICE),
                ServiceRequirement(KERNEL_STATUS_SERVICE),
            ),
        ),
        setup=setup,
    )


__all__ = ["create_plugin"]
