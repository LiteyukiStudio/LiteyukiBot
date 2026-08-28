"""Public command registration and invocation models."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from liteyukibot_kernel.events import (
    ActionEnvelope,
    EventEnvelope,
    HandlerResult,
    Message,
    Segment,
    SendMessage,
)

from .commands_parsing import CommandParseError, CommandSchema, ParsedCommand, parse_command
from .permissions import PUBLIC


def _validate_token(name: str, value: str) -> None:
    """Validate token.

    Args:
        name: Stable name used to identify the value.
        value: Value to validate, transform, or store.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_validate_token`. It delegates to `strip`, `any`, `isspace`
        while keeping intermediate state local to the owning operation.
    """
    if not isinstance(value, str):
        raise TypeError(f"command {name} must be a string")
    if not value or value != value.strip() or any(character.isspace() for character in value):
        raise ValueError(f"command {name} must be a non-empty token without whitespace")


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """Represent the command spec contract."""
    name: str
    aliases: tuple[str, ...] = ()
    summary: str = ""
    usage: str = ""
    permission: str = PUBLIC
    schema: CommandSchema = CommandSchema()
    path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate and normalize the command spec after initialization.

        Returns:
            None.
        """
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
        if not isinstance(self.schema, CommandSchema):
            raise TypeError("command schema must be CommandSchema")
        if isinstance(self.path, str):
            raise TypeError("command path must be a sequence of tokens")
        path = tuple(self.path)
        for segment in path:
            _validate_token("path segment", segment)
        object.__setattr__(self, "aliases", aliases)
        object.__setattr__(self, "path", path)

    @property
    def command_path(self) -> tuple[str, ...]:
        """Return the command spec's command path.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        return (*self.path, self.name)


@dataclass(frozen=True, slots=True)
class CommandInvocation:
    """Represent the command invocation contract."""
    event: EventEnvelope
    command: str
    invoked_as: str
    prefix: str
    raw_arguments: str
    schema: CommandSchema = CommandSchema()
    command_path: tuple[str, ...] = ()
    _parsed: ParsedCommand | None = field(default=None, repr=False, compare=False)
    _parse_error: CommandParseError | None = field(default=None, repr=False, compare=False)

    def parse(self) -> ParsedCommand:
        """Parse the command invocation operation.

        Returns:
            The `ParsedCommand` result produced by the operation.
        """
        if self._parse_error is not None:
            raise self._parse_error
        if self._parsed is not None:
            return self._parsed
        return parse_command(self.raw_arguments, self.schema)

    def reply(self, message: Message | str) -> HandlerResult:
        """Implement the reply operation for the command invocation.

        Args:
            message: Message content associated with the operation.

        Returns:
            The `HandlerResult` result produced by the operation.
        """
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
    Awaitable[HandlerResult | None],
]

@dataclass(frozen=True, slots=True)
class CommandRegistration:
    """Represent the command registration contract."""
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
