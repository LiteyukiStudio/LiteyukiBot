"""Distribution wrapper for LiteyukiBot's local WebUI assets."""

from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from importlib.resources.abc import Traversable

from .service import (
    WebUiBridge,
    WebUiEvent,
    WebUiEventReplay,
    WebUiPrincipal,
    WebUiServer,
    WebUiServiceError,
    WebUiUnavailableError,
    create_app,
)

__all__ = [
    "__version__",
    "WebUiBridge",
    "WebUiEvent",
    "WebUiEventReplay",
    "WebUiPrincipal",
    "WebUiServer",
    "WebUiServiceError",
    "WebUiUnavailableError",
    "create_app",
    "static_assets",
]

try:
    __version__ = version("liteyukibot-v7-webui")
except PackageNotFoundError:
    __version__ = "0+unknown"


def static_assets() -> Traversable:
    """Return the installed directory that will contain built WebUI assets."""
    return files("liteyukibot_webui").joinpath("static")
