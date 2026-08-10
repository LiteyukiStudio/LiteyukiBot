from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import cast

import pytest
from liteyukibot_commands import (
    ArgumentSpec,
    CommandParseError,
    CommandSchema,
    OptionSpec,
    ValueConverter,
    boolean_value,
    float_value,
    integer_value,
    parse_command,
    tokenize_command,
)


def test_tokenizer_preserves_chat_arguments_without_shell_mode() -> None:
    assert tokenize_command("  alpha\t'hello world' \"\" escaped\\ value 中文  ") == (
        "alpha",
        "hello world",
        "",
        "escaped value",
        "中文",
    )
    assert tokenize_command("'single \\' quote' \"double \\\" quote\"") == (
        "single ' quote",
        'double " quote',
    )


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("value\\", "trailing_escape"),
        ("'value", "unterminated_quote"),
        ('"value', "unterminated_quote"),
    ],
)
def test_tokenizer_reports_stable_errors(value: str, code: str) -> None:
    with pytest.raises(CommandParseError) as raised:
        tokenize_command(value)

    assert raised.value.code == code


def test_schema_parses_typed_arguments_options_flags_and_repeats() -> None:
    schema = CommandSchema(
        arguments=(
            ArgumentSpec("count", converter=integer_value),
            ArgumentSpec("label", required=False, default="default"),
            ArgumentSpec("items", converter=float_value, required=False, variadic=True),
        ),
        options=(
            OptionSpec("name", aliases=("n",), required=True),
            OptionSpec("enabled", aliases=("e",), converter=boolean_value),
            OptionSpec("verbose", aliases=("v",), flag=True),
            OptionSpec("tag", aliases=("t",), repeatable=True),
            OptionSpec("debug", aliases=("d",), flag=True, repeatable=True),
        ),
    )

    parsed = parse_command(
        "3 title 1.5 2 --name=alpha -e false -v -t one --tag two -d -d",
        schema,
    )

    assert parsed.arguments == {"count": 3, "label": "title", "items": (1.5, 2.0)}
    assert parsed.options == {
        "name": "alpha",
        "enabled": False,
        "verbose": True,
        "tag": ("one", "two"),
        "debug": 2,
    }
    assert isinstance(parsed.arguments, MappingProxyType)
    assert isinstance(parsed.options, MappingProxyType)
    with pytest.raises(TypeError):
        parsed.options["name"] = "changed"


def test_parser_applies_defaults_and_option_terminator() -> None:
    schema = CommandSchema(
        arguments=(ArgumentSpec("value"),),
        options=(
            OptionSpec("limit", aliases=("l",), converter=integer_value, default=10),
            OptionSpec("quiet", aliases=("q",), flag=True),
            OptionSpec("include", aliases=("i",), repeatable=True),
        ),
    )

    parsed = parse_command("-- --literal", schema)

    assert parsed.arguments == {"value": "--literal"}
    assert parsed.options == {"limit": 10, "quiet": False, "include": ()}


def test_parser_consumes_negative_option_values() -> None:
    schema = CommandSchema(options=(OptionSpec("offset", aliases=("o",), converter=integer_value),))

    assert parse_command("--offset -2", schema).options["offset"] == -2
    assert parse_command("-o=-3", schema).options["offset"] == -3


@pytest.mark.parametrize(
    ("value", "schema", "code", "subject"),
    [
        ("--missing", CommandSchema(), "unknown_option", None),
        ("--name", CommandSchema(options=(OptionSpec("name"),)), "missing_option_value", "name"),
        (
            "--name one --name two",
            CommandSchema(options=(OptionSpec("name"),)),
            "duplicate_option",
            "name",
        ),
        (
            "",
            CommandSchema(options=(OptionSpec("name", required=True),)),
            "missing_option",
            "name",
        ),
        ("", CommandSchema(arguments=(ArgumentSpec("value"),)), "missing_argument", "value"),
        ("one two", CommandSchema(arguments=(ArgumentSpec("value"),)), "unexpected_argument", None),
        (
            "invalid",
            CommandSchema(arguments=(ArgumentSpec("value", converter=integer_value),)),
            "invalid_value",
            "value",
        ),
        (
            "--verbose=true",
            CommandSchema(options=(OptionSpec("verbose", flag=True),)),
            "unexpected_option_value",
            "verbose",
        ),
    ],
)
def test_parser_reports_stable_error_codes(
    value: str,
    schema: CommandSchema,
    code: str,
    subject: str | None,
) -> None:
    with pytest.raises(CommandParseError) as raised:
        parse_command(value, schema)

    assert raised.value.code == code
    assert raised.value.subject == subject
    if code == "invalid_value":
        assert isinstance(raised.value.__cause__, ValueError)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: ArgumentSpec("bad name"), "argument name"),
        (lambda: ArgumentSpec("value", converter=cast(ValueConverter, 1)), "converter must be callable"),
        (lambda: ArgumentSpec("value", default=1), "must not have a default"),
        (lambda: ArgumentSpec("values", variadic=True, default=()), "must not have a default"),
        (lambda: OptionSpec("bad=name"), "option name"),
        (lambda: OptionSpec("name", aliases=("long",)), "must be one character"),
        (lambda: OptionSpec("name", aliases=("n", "n")), "duplicate alias"),
        (lambda: OptionSpec("name", flag=True, default=False), "must not have a default"),
        (
            lambda: CommandSchema(arguments=(ArgumentSpec("one"), ArgumentSpec("one"))),
            "duplicate command argument",
        ),
        (
            lambda: CommandSchema(
                arguments=(
                    ArgumentSpec("optional", required=False),
                    ArgumentSpec("required"),
                )
            ),
            "must not follow an optional",
        ),
        (
            lambda: CommandSchema(
                arguments=(
                    ArgumentSpec("values", required=False, variadic=True),
                    ArgumentSpec("after", required=False),
                )
            ),
            "must be last",
        ),
        (
            lambda: CommandSchema(options=(OptionSpec("one", aliases=("x",)), OptionSpec("two", aliases=("x",)))),
            "duplicate command option alias",
        ),
    ],
)
def test_schema_rejects_ambiguous_definitions(factory: Callable[[], object], message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("TRUE", True), ("false", False), ("False", False)],
)
def test_strict_boolean_converter(value: str, expected: bool) -> None:
    assert boolean_value(value) is expected


def test_strict_boolean_converter_rejects_implicit_values() -> None:
    with pytest.raises(ValueError, match="true or false"):
        boolean_value("yes")
