"""Essential help and status commands for LiteyukiBot v7."""

from importlib.metadata import PackageNotFoundError, version

from .plugin import create_plugin
from .render import Language, render_help, render_status

try:
    __version__ = version("liteyukibot-v7-essentials")
except PackageNotFoundError:
    __version__ = "0.1.0a1"

plugin = create_plugin(__version__)

__all__ = [
    "Language",
    "__version__",
    "plugin",
    "render_help",
    "render_status",
]
