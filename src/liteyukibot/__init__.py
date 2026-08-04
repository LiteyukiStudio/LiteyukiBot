"""LiteyukiBot v7 public API."""

from .app import LiteyukiApp
from .plugins import PluginContext, PluginDefinition, PluginHandle, PluginManifest
from .services import ServiceKey, ServiceRegistry, ServiceRequirement

__all__ = [
    "LiteyukiApp",
    "PluginContext",
    "PluginDefinition",
    "PluginHandle",
    "PluginManifest",
    "ServiceKey",
    "ServiceRegistry",
    "ServiceRequirement",
]

__version__ = "7.0.0.dev0"
