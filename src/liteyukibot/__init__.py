"""LiteyukiBot v7 public API."""

from ._version import __version__
from .app import LiteyukiApp
from .plugins import (
    PluginContext,
    PluginDefinition,
    PluginHandle,
    PluginManifest,
    PluginPaths,
    PluginServices,
)
from .services import ServiceKey, ServiceRegistry, ServiceRequirement
from .status import KERNEL_STATUS_SERVICE, KernelStatusProvider, KernelStatusSnapshot

__all__ = [
    "LiteyukiApp",
    "KERNEL_STATUS_SERVICE",
    "KernelStatusProvider",
    "KernelStatusSnapshot",
    "PluginContext",
    "PluginDefinition",
    "PluginHandle",
    "PluginManifest",
    "PluginPaths",
    "PluginServices",
    "ServiceKey",
    "ServiceRegistry",
    "ServiceRequirement",
    "__version__",
]
