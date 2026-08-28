"""Built-in help and status commands implemented directly on Cordis."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from liteyukibot_cordis import Scope
from liteyukibot_kernel import KERNEL_STATUS_SERVICE
from liteyukibot_kernel.events import HandlerResult
from liteyukibot_kernel.status import KernelStatusProvider

from liteyukibot.i18n import I18N_SERVICE

from .commands import (
    COMMAND_SERVICE,
    ArgumentSpec,
    CommandBinding,
    CommandInvocation,
    CommandParseError,
    CommandSchema,
    CommandService,
    CommandSpec,
)
from .common import LOGGER_PROVIDER, NullLogger, NullTranslator, optional_use
from .essentials_render import Language, messages, render_help, render_parse_error, render_status
from .permissions import Principal
from .profile import PROFILE_SERVICE

_PUBLIC_PERMISSION = "public"
_STATUS_READ_CAPABILITY = "liteyukibot.status.read"


def _language(config: Mapping[str, object]) -> Language:
    unknown = set(config) - {"language"}
    if unknown:
        raise ValueError(f"unknown essentials config keys: {', '.join(sorted(unknown))}")
    value = config.get("language", "zh-CN")
    if value not in {"zh-CN", "en"}:
        raise ValueError("essentials language must be 'zh-CN' or 'en'")
    return cast(Language, value)


async def activate(scope: Scope) -> None:
    """Register help/status commands owned by this feature scope."""
    command_service = cast(CommandService, await scope.use(COMMAND_SERVICE))
    status_provider = cast(KernelStatusProvider, await scope.use(KERNEL_STATUS_SERVICE))
    profile_service = await optional_use(scope, PROFILE_SERVICE, None)
    translator = await optional_use(scope, I18N_SERVICE, NullTranslator())
    logger = await optional_use(scope, LOGGER_PROVIDER, NullLogger())
    language = _language(scope.config)
    text = messages(language, translator)

    async def event_language(invocation: CommandInvocation) -> Language:
        if profile_service is None or invocation.event.actor is None:
            return language
        try:
            profile = await profile_service.get(
                Principal(invocation.event.runtime_id, invocation.event.bot_id, invocation.event.actor.id)
            )
        except Exception:
            logger.warning("profile language lookup failed; using essentials default", event_id=invocation.event.id)
            return language
        return cast(Language, profile.language) if profile.language in {"zh-CN", "en"} else language

    async def help_command(invocation: CommandInvocation) -> HandlerResult:
        current_language = await event_language(invocation)
        try:
            parsed = invocation.parse()
        except CommandParseError as error:
            return invocation.reply(render_parse_error(error, language=current_language, translator=translator))
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
                translator=translator,
                target=target or None,
            )
        )

    async def status_command(invocation: CommandInvocation) -> HandlerResult:
        return invocation.reply(
            render_status(status_provider.snapshot(), language=await event_language(invocation), translator=translator)
        )

    bindings: tuple[CommandBinding, ...] = (
        (
            CommandSpec(
                "help",
                aliases=("帮助",),
                summary=text.help_summary,
                permission=_PUBLIC_PERMISSION,
                schema=CommandSchema(arguments=(ArgumentSpec("path", required=False, variadic=True),)),
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
    command_service.register_many(bindings, owner=scope.plugin_id)
    async def unregister() -> None:
        command_service.unregister_owner(scope.plugin_id)

    scope.own(unregister)


__all__ = [
    "Language",
    "activate",
    "messages",
    "render_help",
    "render_parse_error",
    "render_status",
]
