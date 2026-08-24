"""Distribution wrapper for LiteyukiBot's local WebUI assets."""

from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from importlib.resources.abc import Traversable

from liteyukibot.resource_packs import ResourcePackDeclaration

from .service import (
    WebUiBridge,
    WebUiEvent,
    WebUiEventReplay,
    WebUiPrincipal,
    WebUiServer,
    WebUiServiceError,
    WebUiUnavailableError,
    WebUiUploadPolicy,
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
    "WebUiUploadPolicy",
    "create_app",
    "static_assets",
    "resource_pack_declarations",
]

try:
    __version__ = version("liteyukibot-v7-webui")
except PackageNotFoundError:
    __version__ = "0+unknown"


def static_assets() -> Traversable:
    """Return the installed directory that will contain built WebUI assets.

    Returns:
        The `Traversable` result produced by the operation.
    """
    return files("liteyukibot_webui").joinpath("static")


def resource_pack_declarations() -> tuple[ResourcePackDeclaration, ...]:
    """Return the package-owned resource packs enabled by the host.

    Returns:
        Result produced by this callable.
    """
    return (ResourcePackDeclaration("liteyukibot_webui", "resources"),)
