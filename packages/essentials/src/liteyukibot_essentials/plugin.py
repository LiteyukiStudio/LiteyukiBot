"""Native plugin entry point for essential commands."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, cast

from liteyukibot_commands import (
    COMMAND_SERVICE,
    ArgumentSpec,
    CommandBinding,
    CommandInvocation,
    CommandParseError,
    CommandSchema,
    CommandService,
    CommandSpec,
)
from liteyukibot_permissions import Principal

from liteyukibot import PluginContext, PluginDefinition, PluginHandle, PluginManifest
from liteyukibot.events import HandlerResult
from liteyukibot.services import ServiceKey, ServiceRequirement
from liteyukibot.status import KERNEL_STATUS_SERVICE, KernelStatusProvider

from .render import Language, messages, render_help, render_parse_error, render_status

_PUBLIC_PERMISSION = "public"
_STATUS_READ_CAPABILITY = "liteyukibot.status.read"
_PROFILE_SERVICE = ServiceKey("liteyukibot.profile", 1)


class _ProfileSnapshot(Protocol):
    language: str


class _ProfileService(Protocol):
    async def get(self, principal: Principal) -> _ProfileSnapshot: ...


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
    profile_service = cast(_ProfileService | None, context.services.get_optional(_PROFILE_SERVICE))
    text = messages(language)

    async def event_language(invocation: CommandInvocation) -> Language:
        if profile_service is None or invocation.event.actor is None:
            return language
        try:
            profile = await profile_service.get(
                Principal(invocation.event.runtime_id, invocation.event.bot_id, invocation.event.actor.id)
            )
        except Exception:
            context.logger.warning(
                "profile language lookup failed; using essentials default",
                event_id=invocation.event.id,
            )
            return language
        return cast(Language, profile.language) if profile.language in {"zh-CN", "en"} else language

    async def help_command(invocation: CommandInvocation) -> HandlerResult:
        current_language = await event_language(invocation)
        try:
            parsed = invocation.parse()
        except CommandParseError as error:
            return invocation.reply(render_parse_error(error, language=current_language))
        target = cast(tuple[str, ...], parsed.arguments["path"])
        visible = command_service.visible(invocation.event)
        if target:
            registration = command_service.resolve(invocation.event, target)
            if registration is None:
                visible = ()
            else:
                visible = (registration,)
                target = registration.spec.command_path
        return invocation.reply(
            render_help(
                visible,
                prefix=invocation.prefix,
                language=current_language,
                target=target or None,
            )
        )

    async def status_command(invocation: CommandInvocation) -> HandlerResult:
        return invocation.reply(render_status(status_provider.snapshot(), language=await event_language(invocation)))

    bindings: tuple[CommandBinding, ...] = (
        (
            CommandSpec(
                "help",
                aliases=("帮助",),
                summary=text.help_summary,
                permission=_PUBLIC_PERMISSION,
                schema=CommandSchema(
                    arguments=(ArgumentSpec("path", required=False, variadic=True),),
                ),
            ),
            help_command,
        ),
        (
            CommandSpec(
                "status",
                aliases=("状态",),
                summary=text.status_summary,
                permission=_STATUS_READ_CAPABILITY,
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
                ServiceRequirement(_PROFILE_SERVICE, optional=True),
            ),
        ),
        setup=setup,
    )


__all__ = ["create_plugin"]
