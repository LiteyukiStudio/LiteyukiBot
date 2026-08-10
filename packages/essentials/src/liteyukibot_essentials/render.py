"""Deterministic plain-text rendering for essential commands."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from liteyukibot_commands import CommandRegistration

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


_MESSAGES: dict[Language, _Messages] = {
    "zh-CN": _Messages(
        help_summary="显示可用命令",
        status_summary="显示内核状态",
        help_header="可用命令：",
        state="状态",
        uptime="运行时间",
        outstanding="待处理事件",
        plugins="插件",
        runtimes="运行时",
        seconds="秒",
        empty="无",
    ),
    "en": _Messages(
        help_summary="Show available commands",
        status_summary="Show kernel status",
        help_header="Available commands:",
        state="State",
        uptime="Uptime",
        outstanding="Outstanding events",
        plugins="Plugins",
        runtimes="Runtimes",
        seconds="seconds",
        empty="none",
    ),
}


def messages(language: Language) -> _Messages:
    return _MESSAGES[language]


def render_help(
    registrations: tuple[CommandRegistration, ...],
    *,
    prefix: str,
    language: Language,
) -> str:
    text = messages(language)
    lines = [text.help_header]
    ordered = sorted(
        registrations,
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


def render_status(snapshot: KernelStatusSnapshot, *, language: Language) -> str:
    text = messages(language)
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


__all__ = ["Language", "messages", "render_help", "render_status"]
