"""Distribution wrapper for LiteyukiBot's local WebUI assets."""

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


def static_assets() -> Traversable:
    """Return the installed directory that will contain built WebUI assets."""
    return files("liteyukibot_webui").joinpath("static")
