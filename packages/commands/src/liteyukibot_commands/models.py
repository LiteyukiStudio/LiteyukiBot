"""Public command registration and invocation models."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from liteyukibot_permissions import PUBLIC

from liteyukibot.events import (
    ActionEnvelope,
    EventEnvelope,
    HandlerResult,
    Message,
    Segment,
    SendMessage,
)


def _validate_token(name: str, value: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"command {name} must be a string")
    if not value or value != value.strip() or any(character.isspace() for character in value):
        raise ValueError(f"command {name} must be a non-empty token without whitespace")


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    aliases: tuple[str, ...] = ()
    summary: str = ""
    usage: str = ""
    permission: str = PUBLIC

    def __post_init__(self) -> None:
        _validate_token("name", self.name)
        if isinstance(self.aliases, str):
            raise TypeError("command aliases must be a sequence of tokens")
        aliases = tuple(self.aliases)
        seen = {self.name.casefold()}
        for alias in aliases:
            if not isinstance(alias, str):
                raise TypeError("command aliases must be strings")
            _validate_token("alias", alias)
            normalized = alias.casefold()
            if normalized in seen:
                raise ValueError(f"duplicate command name or alias: {alias}")
            seen.add(normalized)
        if not isinstance(self.summary, str) or not isinstance(self.usage, str):
            raise TypeError("command summary and usage must be strings")
        if not isinstance(self.permission, str):
            raise TypeError("command permission must be a string")
        if not self.permission or self.permission != self.permission.strip():
            raise ValueError("command permission must be a non-empty trimmed string")
        object.__setattr__(self, "aliases", aliases)


@dataclass(frozen=True, slots=True)
class CommandInvocation:
    event: EventEnvelope
    command: str
    invoked_as: str
    raw_arguments: str

    def reply(self, message: Message | str) -> HandlerResult:
        if isinstance(message, str):
            message = Message(segments=(Segment(type="text", data={"text": message}),))
        return HandlerResult(
            actions=(
                ActionEnvelope(
                    event_id=self.event.id,
                    runtime_id=self.event.runtime_id,
                    bot_id=self.event.bot_id,
                    action=SendMessage(
                        message=message,
                        conversation=self.event.conversation,
                        reply_token=self.event.reply_token,
                    ),
                ),
            ),
            stop_propagation=True,
        )


type CommandHandler = Callable[
    [CommandInvocation],
    Awaitable[HandlerResult | None] | HandlerResult | None,
]


@dataclass(frozen=True, slots=True)
class CommandRegistration:
    id: int
    owner: str
    spec: CommandSpec


type CommandBinding = tuple[CommandSpec, CommandHandler]


__all__ = [
    "CommandBinding",
    "CommandHandler",
    "CommandInvocation",
    "CommandRegistration",
    "CommandSpec",
]
