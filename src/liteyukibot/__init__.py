"""LiteyukiBot v7 public API."""

from ._version import __version__
from .app import LiteyukiApp
from .functions import FUNCTION_DISPATCH_SERVICE, FunctionCall, FunctionDispatcher
from .i18n import I18N_SERVICE, Translator
from .init_specs import InitFieldKind, InitFieldSpec, PluginInitSpec, RuntimeInitSpec
from .management import MANAGEMENT_SERVICE, ManagementCommand, ManagementRegistry
from .plugins import (
    PluginContext,
    PluginDefinition,
    PluginHandle,
    PluginManifest,
    PluginPaths,
    PluginServices,
)
from .resource_packs import RESOURCE_CATALOG_SERVICE, ResourceCatalog, ResourcePackDeclaration
from .services import ServiceKey, ServiceRegistry, ServiceRequirement
from .status import KERNEL_STATUS_SERVICE, KernelStatusProvider, KernelStatusSnapshot

__all__ = [
    "LiteyukiApp",
    "KERNEL_STATUS_SERVICE",
    "KernelStatusProvider",
    "KernelStatusSnapshot",
    "InitFieldKind",
    "InitFieldSpec",
    "PluginContext",
    "PluginDefinition",
    "PluginHandle",
    "PluginManifest",
    "PluginInitSpec",
    "PluginPaths",
    "PluginServices",
    "ServiceKey",
    "ServiceRegistry",
    "ServiceRequirement",
    "RuntimeInitSpec",
    "FUNCTION_DISPATCH_SERVICE",
    "FunctionCall",
    "FunctionDispatcher",
    "I18N_SERVICE",
    "MANAGEMENT_SERVICE",
    "ManagementCommand",
    "ManagementRegistry",
    "RESOURCE_CATALOG_SERVICE",
    "ResourceCatalog",
    "ResourcePackDeclaration",
    "Translator",
    "__version__",
]
