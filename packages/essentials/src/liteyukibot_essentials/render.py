"""Deterministic plain-text rendering for essential commands."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from liteyukibot_commands import ArgumentSpec, CommandParseError, CommandRegistration, OptionSpec

from liteyukibot.i18n import Translator
from liteyukibot.status import KernelStatusSnapshot

type Language = Literal["zh-CN", "en"]


@dataclass(frozen=True, slots=True)
class _Messages:
    help_summary: str
    status_summary: str
    help_header: str
    state: str
    uptime: str
    outstanding: str
    plugins: str
    runtimes: str
    seconds: str
    empty: str
    command_not_found: str
    invalid_command: str
    aliases: str
    usage: str
    arguments: str
    options: str
    required: str
    optional: str


def messages(language: Language, translator: Translator) -> _Messages:
    locale = "en-US" if language == "en" else language
    return _Messages(
        **{
            field: translator.text_for(locale, f"essentials.{field}", field.replace("_", " "))
            for field in _Messages.__dataclass_fields__
        }
    )


def render_help(
    registrations: tuple[CommandRegistration, ...],
    *,
    prefix: str,
    language: Language,
    translator: Translator,
    target: tuple[str, ...] | None = None,
) -> str:
    text = messages(language, translator)
    lines = [text.help_header]
    selected = registrations if target is None else tuple(
        registration for registration in registrations if registration.spec.command_path == target
    )
    if target is not None and not selected:
        return text.command_not_found
    if target is not None:
        registration = selected[0]
        spec = registration.spec
        label = prefix + " ".join(spec.command_path)
        lines = [label]
        if spec.aliases:
            lines.append(
                text.aliases + ": " + ", ".join(prefix + " ".join((*spec.path, alias)) for alias in spec.aliases)
            )
        if spec.summary:
            lines.append(spec.summary)
        lines.append(f"{text.usage}: {spec.usage or _usage(label, spec.schema.arguments, spec.schema.options)}")
        if spec.schema.arguments:
            lines.append(text.arguments + ":")
            lines.extend(_render_argument(argument, text) for argument in spec.schema.arguments)
        if spec.schema.options:
            lines.append(text.options + ":")
            lines.extend(_render_option(option, text) for option in spec.schema.options)
        return "\n".join(lines)
    ordered = sorted(
        (item for item in selected if not item.spec.path),
        key=lambda item: (item.spec.name.casefold(), item.id),
    )
    for registration in ordered:
        spec = registration.spec
        label = f"{prefix}{spec.name}"
        if spec.aliases:
            aliases = ", ".join(f"{prefix}{alias}" for alias in spec.aliases)
            label = f"{label} ({aliases})"
        lines.append(f"{label} - {spec.summary}" if spec.summary else label)
    return "\n".join(lines)


def render_parse_error(error: CommandParseError, *, language: Language, translator: Translator) -> str:
    return messages(language, translator).invalid_command


def _usage(label: str, arguments: tuple[ArgumentSpec, ...], options: tuple[OptionSpec, ...]) -> str:
    positional = []
    for argument in arguments:
        name = argument.metavar or argument.name.upper()
        if argument.variadic:
            name = f"{name}..."
        positional.append(f"<{name}>" if argument.required else f"[{name}]")
    option_usage = []
    for option in options:
        label_text = f"--{option.name}" if option.flag else f"--{option.name} {option.metavar or option.name.upper()}"
        option_usage.append(label_text if option.required else f"[{label_text}]")
    return " ".join((label, *positional, *option_usage))


def _render_argument(argument: ArgumentSpec, text: _Messages) -> str:
    label = argument.metavar or argument.name
    requirement = text.required if argument.required else text.optional
    suffix = "..." if argument.variadic else ""
    return f"- {label}{suffix} ({requirement})"


def _render_option(option: OptionSpec, text: _Messages) -> str:
    labels = [f"--{option.name}", *(f"-{alias}" for alias in option.aliases)]
    requirement = text.required if option.required else text.optional
    suffix = " repeatable" if option.repeatable else ""
    return f"- {', '.join(labels)} ({requirement}{suffix})"


def render_status(snapshot: KernelStatusSnapshot, *, language: Language, translator: Translator) -> str:
    text = messages(language, translator)
    lines = [
        f"LiteyukiBot {snapshot.version}",
        f"{text.state}: {snapshot.state}",
        f"{text.uptime}: {snapshot.uptime_seconds:.3f} {text.seconds}",
        f"{text.outstanding}: {snapshot.events_outstanding}",
        f"{text.plugins}:",
        *_render_states(snapshot.plugins, empty=text.empty),
        f"{text.runtimes}:",
        *_render_states(snapshot.runtimes, empty=text.empty),
    ]
    return "\n".join(lines)


def _render_states(states: Mapping[str, str], *, empty: str) -> tuple[str, ...]:
    items = sorted(states.items())
    if not items:
        return (f"- {empty}",)
    return tuple(f"- {identifier}: {state}" for identifier, state in items)


__all__ = ["Language", "messages", "render_help", "render_parse_error", "render_status"]
