"""Protocol-neutral command routing for LiteyukiBot v7."""

from importlib.metadata import PackageNotFoundError, version

from .models import (
    CommandBinding,
    CommandHandler,
    CommandInvocation,
    CommandRegistration,
    CommandSpec,
)
from .parsing import (
    ArgumentSpec,
    CommandParseError,
    CommandSchema,
    OptionSpec,
    ParsedCommand,
    ValueConverter,
    boolean_value,
    float_value,
    integer_value,
    parse_command,
    string_value,
    tokenize_command,
)
from .plugin import create_plugin
from .service import COMMAND_SERVICE, CommandService

try:
    __version__ = version("liteyukibot-v7-commands")
except PackageNotFoundError:
    __version__ = "0.2.0a1"

plugin = create_plugin(__version__)

__all__ = [
    "COMMAND_SERVICE",
    "ArgumentSpec",
    "CommandBinding",
    "CommandHandler",
    "CommandInvocation",
    "CommandParseError",
    "CommandRegistration",
    "CommandService",
    "CommandSchema",
    "CommandSpec",
    "OptionSpec",
    "ParsedCommand",
    "ValueConverter",
    "__version__",
    "plugin",
    "boolean_value",
    "float_value",
    "integer_value",
    "parse_command",
    "string_value",
    "tokenize_command",
]
