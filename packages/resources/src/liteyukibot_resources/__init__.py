"""Declarative resource management for LiteyukiBot v7 plugins."""

from importlib.metadata import PackageNotFoundError, version

from .models import (
    ResourceField,
    ResourceOperation,
    ResourceProvider,
    ResourceRegistration,
    ResourceSpec,
)
from .plugin import create_plugin
from .service import RESOURCE_SERVICE, ResourceError, ResourceService

try:
    __version__ = version("liteyukibot-v7-resources")
except PackageNotFoundError:
    __version__ = "0.2.0a1"

plugin = create_plugin(__version__)

__all__ = [
    "RESOURCE_SERVICE",
    "ResourceField",
    "ResourceError",
    "ResourceOperation",
    "ResourceProvider",
    "ResourceRegistration",
    "ResourceService",
    "ResourceSpec",
    "__version__",
    "plugin",
]
