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

from liteyukibot import (
    AuthorizationContext,
    InitFieldKind,
    InitFieldSpec,
    PluginContext,
    PluginDefinition,
    PluginInitSpec,
    PluginManifest,
    ToolDeclaration,
)
from liteyukibot.events import HandlerResult
from liteyukibot.i18n import I18N_SERVICE, Translator
from liteyukibot.plugins import ToolCallback
from liteyukibot.resource_packs import ResourcePackDeclaration
from liteyukibot.services import ServiceKey, ServiceRequirement
from liteyukibot.status import KERNEL_STATUS_SERVICE, KernelStatusProvider

from .render import Language, messages, render_help, render_parse_error, render_status

_PUBLIC_PERMISSION = "public"
_STATUS_READ_CAPABILITY = "liteyukibot.status.read"
_PROFILE_SERVICE = ServiceKey("liteyukibot.profile", 2)


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


async def setup(context: PluginContext) -> None:
    if any(context.config.get(key) == 1 for key in ("api_version", "schema_version", "version")):
        raise RuntimeError("migration_required")
    language = _language(context.config)
    command_service = cast(CommandService, context.services.require(COMMAND_SERVICE))
    status_provider = cast(KernelStatusProvider, context.services.require(KERNEL_STATUS_SERVICE))
    profile_service = cast(_ProfileService | None, context.services.get_optional(_PROFILE_SERVICE))
    translator = cast(Translator, context.services.require(I18N_SERVICE))
    text = messages(language, translator)

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
    command_service.register_many(bindings, owner=context.id)
    context.defer_cleanup(lambda: command_service.unregister_owner(context.id))

    async def help_tool(authorization: AuthorizationContext, _arguments: Mapping[str, Any]) -> dict[str, object]:
        return {
            "commands": [
                {
                    "path": list(registration.spec.command_path),
                    "summary": registration.spec.summary,
                }
                for registration in command_service.visible_context(authorization)
            ]
        }

    async def status_tool(_authorization: AuthorizationContext, _arguments: Mapping[str, Any]) -> dict[str, object]:
        snapshot = status_provider.snapshot()
        return {
            "version": snapshot.version,
            "state": snapshot.state,
            "uptime_seconds": snapshot.uptime_seconds,
            "plugins": dict(snapshot.plugins),
            "runtimes": dict(snapshot.runtimes),
            "events_outstanding": snapshot.events_outstanding,
        }

    context.register_tool("liteyukibot.essentials.help", cast(ToolCallback, help_tool))
    context.register_tool("liteyukibot.essentials.status", cast(ToolCallback, status_tool))


def create_plugin(version: str) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id="liteyukibot.essentials",
            name="LiteyukiBot Essentials",
            version=version,
            resource_packs=(ResourcePackDeclaration("liteyukibot_essentials"),),
            requires=(
                ServiceRequirement(COMMAND_SERVICE),
                ServiceRequirement(KERNEL_STATUS_SERVICE),
                ServiceRequirement(_PROFILE_SERVICE, optional=True),
                ServiceRequirement(I18N_SERVICE),
            ),
            tools=(
                ToolDeclaration(
                    id="liteyukibot.essentials.help",
                    description="List currently registered commands.",
                    input_schema={"type": "object", "additionalProperties": False},
                    output_schema={
                        "type": "object",
                        "properties": {
                            "commands": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "path": {"type": "array", "items": {"type": "string"}},
                                        "summary": {"type": "string"},
                                    },
                                    "required": ["path", "summary"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["commands"],
                        "additionalProperties": False,
                    },
                ),
                ToolDeclaration(
                    id="liteyukibot.essentials.status",
                    description="Read bounded kernel status for the current invocation context.",
                    input_schema={"type": "object", "additionalProperties": False},
                    output_schema={
                        "type": "object",
                        "properties": {
                            "version": {"type": "string"},
                            "state": {"type": "string"},
                            "uptime_seconds": {"type": "number", "minimum": 0},
                            "plugins": {"type": "object", "additionalProperties": {"type": "string"}},
                            "runtimes": {"type": "object", "additionalProperties": {"type": "string"}},
                            "events_outstanding": {"type": "integer", "minimum": 0},
                        },
                        "required": [
                            "version",
                            "state",
                            "uptime_seconds",
                            "plugins",
                            "runtimes",
                            "events_outstanding",
                        ],
                        "additionalProperties": False,
                    },
                    capabilities=(_STATUS_READ_CAPABILITY,),
                ),
            ),
        ),
        setup=setup,
        init_spec=PluginInitSpec(
            description="Help and protected kernel status commands.",
            fields=(
                InitFieldSpec(
                    key="language",
                    label="Default language",
                    label_key="essentials.init.language",
                    kind=InitFieldKind.STRING,
                    default="zh-CN",
                    choices=("zh-CN", "en"),
                ),
            ),
        ),
    )


__all__ = ["create_plugin"]
