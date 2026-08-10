"""Explicit command tokenization, schemas, and typed value parsing."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

type ValueConverter = Callable[[str], object]


def _validate_name(kind: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"command {kind} must be a string")
    if (
        not value
        or value != value.strip()
        or any(character.isspace() for character in value)
        or value.startswith("-")
        or "=" in value
    ):
        raise ValueError(f"command {kind} must be a non-empty token without whitespace, leading dashes, or equals")
    return value


def string_value(value: str) -> str:
    return value


def integer_value(value: str) -> int:
    return int(value, 10)


def float_value(value: str) -> float:
    return float(value)


def boolean_value(value: str) -> bool:
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError("boolean value must be true or false")


@dataclass(frozen=True, slots=True)
class ArgumentSpec:
    name: str
    converter: ValueConverter = string_value
    required: bool = True
    default: object = None
    variadic: bool = False
    metavar: str = ""

    def __post_init__(self) -> None:
        _validate_name("argument name", self.name)
        if not callable(self.converter):
            raise TypeError(f"command argument {self.name} converter must be callable")
        if not isinstance(self.required, bool) or not isinstance(self.variadic, bool):
            raise TypeError(f"command argument {self.name} required and variadic must be booleans")
        if self.required and self.default is not None:
            raise ValueError(f"required command argument {self.name} must not have a default")
        if self.variadic and self.default is not None:
            raise ValueError(f"variadic command argument {self.name} must not have a default")
        if not isinstance(self.metavar, str):
            raise TypeError(f"command argument {self.name} metavar must be a string")


@dataclass(frozen=True, slots=True)
class OptionSpec:
    name: str
    aliases: tuple[str, ...] = ()
    converter: ValueConverter = string_value
    required: bool = False
    flag: bool = False
    repeatable: bool = False
    default: object = None
    metavar: str = ""

    def __post_init__(self) -> None:
        _validate_name("option name", self.name)
        if isinstance(self.aliases, str):
            raise TypeError(f"command option {self.name} aliases must be a sequence")
        aliases = tuple(self.aliases)
        seen: set[str] = set()
        for alias in aliases:
            _validate_name(f"option {self.name} alias", alias)
            if len(alias) != 1:
                raise ValueError(f"command option {self.name} alias must be one character")
            if alias in seen:
                raise ValueError(f"command option {self.name} has duplicate alias {alias}")
            seen.add(alias)
        if not callable(self.converter):
            raise TypeError(f"command option {self.name} converter must be callable")
        if not all(isinstance(value, bool) for value in (self.required, self.flag, self.repeatable)):
            raise TypeError(f"command option {self.name} required, flag, and repeatable must be booleans")
        if (self.flag or self.repeatable) and self.default is not None:
            raise ValueError(f"flag or repeatable command option {self.name} must not have a default")
        if not isinstance(self.metavar, str):
            raise TypeError(f"command option {self.name} metavar must be a string")
        object.__setattr__(self, "aliases", aliases)


@dataclass(frozen=True, slots=True)
class CommandSchema:
    arguments: tuple[ArgumentSpec, ...] = ()
    options: tuple[OptionSpec, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.arguments, (str, bytes)) or isinstance(self.options, (str, bytes)):
            raise TypeError("command schema arguments and options must be sequences")
        arguments = tuple(self.arguments)
        options = tuple(self.options)
        if any(not isinstance(item, ArgumentSpec) for item in arguments):
            raise TypeError("command schema arguments must contain ArgumentSpec")
        if any(not isinstance(item, OptionSpec) for item in options):
            raise TypeError("command schema options must contain OptionSpec")

        argument_names: set[str] = set()
        optional_seen = False
        for index, argument in enumerate(arguments):
            if argument.name in argument_names:
                raise ValueError(f"duplicate command argument name: {argument.name}")
            argument_names.add(argument.name)
            if argument.variadic and index != len(arguments) - 1:
                raise ValueError(f"variadic command argument {argument.name} must be last")
            if optional_seen and argument.required:
                raise ValueError(f"required command argument {argument.name} must not follow an optional argument")
            optional_seen = optional_seen or not argument.required

        option_names: set[str] = set()
        aliases: set[str] = set()
        for option in options:
            if option.name in option_names:
                raise ValueError(f"duplicate command option name: {option.name}")
            option_names.add(option.name)
            conflict = next((alias for alias in option.aliases if alias in aliases), None)
            if conflict is not None:
                raise ValueError(f"duplicate command option alias: {conflict}")
            aliases.update(option.aliases)

        object.__setattr__(self, "arguments", arguments)
        object.__setattr__(self, "options", options)


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    arguments: Mapping[str, object]
    options: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))


class CommandParseError(ValueError):
    def __init__(self, code: str, *, subject: str | None = None, token: str | None = None) -> None:
        self.code = code
        self.subject = subject
        self.token = token
        parts = [code]
        if subject is not None:
            parts.append(subject)
        if token is not None:
            parts.append(repr(token))
        super().__init__(": ".join(parts))


def tokenize_command(value: str) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise TypeError("command input must be a string")
    tokens: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    escaping = False
    started = False
    for character in value:
        if escaping:
            buffer.append(character)
            escaping = False
            started = True
            continue
        if character == "\\":
            escaping = True
            started = True
            continue
        if quote is not None:
            if character == quote:
                quote = None
            else:
                buffer.append(character)
            started = True
            continue
        if character in {"'", '"'}:
            quote = character
            started = True
            continue
        if character.isspace():
            if started:
                tokens.append("".join(buffer))
                buffer.clear()
                started = False
            continue
        buffer.append(character)
        started = True
    if escaping:
        raise CommandParseError("trailing_escape")
    if quote is not None:
        raise CommandParseError("unterminated_quote", token=quote)
    if started:
        tokens.append("".join(buffer))
    return tuple(tokens)


def _converted(converter: ValueConverter, value: str, *, subject: str) -> object:
    try:
        return converter(value)
    except Exception as error:
        raise CommandParseError("invalid_value", subject=subject, token=value) from error


def _option_value(option: OptionSpec, value: str) -> object:
    return _converted(option.converter, value, subject=f"--{option.name}")


def _default_option(option: OptionSpec) -> object:
    if option.flag:
        return 0 if option.repeatable else False
    if option.repeatable:
        return ()
    return option.default


def parse_command(value: str, schema: CommandSchema) -> ParsedCommand:
    if not isinstance(schema, CommandSchema):
        raise TypeError("command schema must be CommandSchema")
    tokens = tokenize_command(value)
    long_options = {option.name: option for option in schema.options}
    short_options = {alias: option for option in schema.options for alias in option.aliases}
    parsed_options: dict[str, object] = {}
    repeated: dict[str, list[object]] = {}
    positional: list[str] = []
    options_enabled = True
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if options_enabled and token == "--":
            options_enabled = False
            index += 1
            continue

        option: OptionSpec | None = None
        inline_value: str | None = None
        if options_enabled and token.startswith("--") and len(token) > 2:
            name, separator, inline = token[2:].partition("=")
            option = long_options.get(name)
            inline_value = inline if separator else None
        elif options_enabled and token.startswith("-") and len(token) > 1:
            name, separator, inline = token[1:].partition("=")
            option = short_options.get(name)
            inline_value = inline if separator else None

        if options_enabled and token.startswith("-") and token != "-":
            if option is None:
                raise CommandParseError("unknown_option", token=token)
            if option.flag:
                if inline_value is not None:
                    raise CommandParseError("unexpected_option_value", subject=option.name, token=inline_value)
                if option.repeatable:
                    current = parsed_options.get(option.name, 0)
                    if not isinstance(current, int):
                        raise RuntimeError(f"command option {option.name} flag count is not an integer")
                    parsed_options[option.name] = current + 1
                elif option.name in parsed_options:
                    raise CommandParseError("duplicate_option", subject=option.name)
                else:
                    parsed_options[option.name] = True
                index += 1
                continue

            if not option.repeatable and option.name in parsed_options:
                raise CommandParseError("duplicate_option", subject=option.name)
            if inline_value is None:
                index += 1
                if index >= len(tokens):
                    raise CommandParseError("missing_option_value", subject=option.name)
                inline_value = tokens[index]
            converted = _option_value(option, inline_value)
            if option.repeatable:
                repeated.setdefault(option.name, []).append(converted)
            else:
                parsed_options[option.name] = converted
            index += 1
            continue

        positional.append(token)
        index += 1

    for name, values in repeated.items():
        parsed_options[name] = tuple(values)
    for option in schema.options:
        if option.name not in parsed_options:
            if option.required:
                raise CommandParseError("missing_option", subject=option.name)
            parsed_options[option.name] = _default_option(option)

    parsed_arguments: dict[str, object] = {}
    position = 0
    for argument in schema.arguments:
        if argument.variadic:
            remaining = positional[position:]
            if argument.required and not remaining:
                raise CommandParseError("missing_argument", subject=argument.name)
            parsed_arguments[argument.name] = tuple(
                _converted(argument.converter, item, subject=argument.name) for item in remaining
            )
            position = len(positional)
            continue
        if position >= len(positional):
            if argument.required:
                raise CommandParseError("missing_argument", subject=argument.name)
            parsed_arguments[argument.name] = argument.default
            continue
        parsed_arguments[argument.name] = _converted(
            argument.converter,
            positional[position],
            subject=argument.name,
        )
        position += 1
    if position < len(positional):
        raise CommandParseError("unexpected_argument", token=positional[position])
    return ParsedCommand(parsed_arguments, parsed_options)


__all__ = [
    "ArgumentSpec",
    "CommandParseError",
    "CommandSchema",
    "OptionSpec",
    "ParsedCommand",
    "ValueConverter",
    "boolean_value",
    "float_value",
    "integer_value",
    "parse_command",
    "string_value",
    "tokenize_command",
]
