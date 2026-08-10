"""Protocol-neutral command routing for LiteyukiBot v7."""

from importlib.metadata import PackageNotFoundError, version

from .models import (
    CommandBinding,
    CommandHandler,
    CommandInvocation,
    CommandRegistration,
    CommandSpec,
)
from .plugin import create_plugin
from .service import COMMAND_SERVICE, CommandService

try:
    __version__ = version("liteyukibot-v7-commands")
except PackageNotFoundError:
    __version__ = "0.1.0a1"

plugin = create_plugin(__version__)

__all__ = [
    "COMMAND_SERVICE",
    "CommandBinding",
    "CommandHandler",
    "CommandInvocation",
    "CommandRegistration",
    "CommandService",
    "CommandSpec",
    "__version__",
    "plugin",
]
