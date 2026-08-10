"""Versioned access policy service for LiteyukiBot v7."""

from importlib.metadata import PackageNotFoundError, version

from .plugin import create_plugin
from .service import OPERATOR, PERMISSION_SERVICE, PUBLIC, PermissionService, Principal

try:
    __version__ = version("liteyukibot-v7-permissions")
except PackageNotFoundError:
    __version__ = "0.1.0a1"

plugin = create_plugin(__version__)

__all__ = [
    "OPERATOR",
    "PERMISSION_SERVICE",
    "PUBLIC",
    "PermissionService",
    "Principal",
    "__version__",
    "plugin",
]
