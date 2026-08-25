"""LiteyukiBot v7 branded facade and compatibility exports."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from ._version import __version__
from .authorization import AuthorizationContext
from .runtime_api import (
    BotSnapshot,
    EventSnapshot,
    RuntimeApiBackend,
    RuntimeApiError,
    RuntimeApiProxy,
    RuntimeBinding,
    RuntimeCallContext,
    RuntimeNamespaceProxy,
    RuntimeRequirement,
    RuntimeUnavailable,
    SendResult,
    create_runtime_proxy,
    invoke_with_runtime,
    runtime,
    runtime_bindings,
    runtime_handler,
    validate_runtime_bindings,
)
from .services import ServiceKey, ServiceRegistry, ServiceRequirement
from .status import KERNEL_STATUS_SERVICE, KernelStatusProvider, KernelStatusSnapshot

if TYPE_CHECKING:
    from .app import LiteyukiApp
    from .functions import (
        AGENT_FUNCTION_CATALOG,
        AGENT_PROMPT_CATALOG,
        AGENT_PROMPT_SELECT,
        FUNCTION_DISPATCH_SERVICE,
        FUNCTION_HOST_ENTRY_POINT_GROUP,
        FUNCTION_LIBRARY_ENTRY_POINT_GROUP,
        FunctionCall,
        FunctionDispatcher,
        FunctionEventContribution,
        FunctionHost,
        FunctionHostBindings,
        FunctionHostProvider,
        FunctionPackSource,
        FunctionPreflight,
        FunctionPromptPreset,
        discover_function_host_provider,
    )
    from .i18n import I18N_SERVICE, Translator
    from .init_specs import InitFieldKind, InitFieldSpec, PluginInitSpec
    from .management import MANAGEMENT_SERVICE, ManagementCommand, ManagementRegistry
    from .operations import (
        ManagementPrincipal,
        OperationConfirmation,
        OperationDefinition,
        OperationImpact,
        OperationLedger,
        OperationRequest,
        OperationState,
        WorkerOperationBridge,
    )
    from .plugins import (
        ExtensionDefinition,
        ExtensionManifest,
        PluginContext,
        PluginDefinition,
        PluginHandle,
        PluginManifest,
        PluginPaths,
        PluginServices,
        ToolDeclaration,
    )
    from .resource_packs import RESOURCE_CATALOG_SERVICE, ResourceCatalog, ResourcePackDeclaration

_LAZY_EXPORTS = {
    "AGENT_FUNCTION_CATALOG": (".functions", "AGENT_FUNCTION_CATALOG"),
    "AGENT_PROMPT_CATALOG": (".functions", "AGENT_PROMPT_CATALOG"),
    "AGENT_PROMPT_SELECT": (".functions", "AGENT_PROMPT_SELECT"),
    "FUNCTION_DISPATCH_SERVICE": (".functions", "FUNCTION_DISPATCH_SERVICE"),
    "FUNCTION_HOST_ENTRY_POINT_GROUP": (".functions", "FUNCTION_HOST_ENTRY_POINT_GROUP"),
    "FUNCTION_LIBRARY_ENTRY_POINT_GROUP": (".functions", "FUNCTION_LIBRARY_ENTRY_POINT_GROUP"),
    "FunctionCall": (".functions", "FunctionCall"),
    "FunctionDispatcher": (".functions", "FunctionDispatcher"),
    "FunctionEventContribution": (".functions", "FunctionEventContribution"),
    "FunctionHost": (".functions", "FunctionHost"),
    "FunctionHostBindings": (".functions", "FunctionHostBindings"),
    "FunctionHostProvider": (".functions", "FunctionHostProvider"),
    "FunctionPackSource": (".functions", "FunctionPackSource"),
    "FunctionPreflight": (".functions", "FunctionPreflight"),
    "FunctionPromptPreset": (".functions", "FunctionPromptPreset"),
    "I18N_SERVICE": (".i18n", "I18N_SERVICE"),
    "InitFieldKind": (".init_specs", "InitFieldKind"),
    "InitFieldSpec": (".init_specs", "InitFieldSpec"),
    "LiteyukiApp": (".app", "LiteyukiApp"),
    "MANAGEMENT_SERVICE": (".management", "MANAGEMENT_SERVICE"),
    "ManagementCommand": (".management", "ManagementCommand"),
    "ManagementPrincipal": (".operations", "ManagementPrincipal"),
    "ManagementRegistry": (".management", "ManagementRegistry"),
    "OperationConfirmation": (".operations", "OperationConfirmation"),
    "OperationDefinition": (".operations", "OperationDefinition"),
    "OperationImpact": (".operations", "OperationImpact"),
    "OperationLedger": (".operations", "OperationLedger"),
    "OperationRequest": (".operations", "OperationRequest"),
    "OperationState": (".operations", "OperationState"),
    "PluginContext": (".plugins", "PluginContext"),
    "PluginDefinition": (".plugins", "PluginDefinition"),
    "PluginHandle": (".plugins", "PluginHandle"),
    "PluginInitSpec": (".init_specs", "PluginInitSpec"),
    "PluginManifest": (".plugins", "PluginManifest"),
    "PluginPaths": (".plugins", "PluginPaths"),
    "PluginServices": (".plugins", "PluginServices"),
    "ExtensionDefinition": (".plugins", "ExtensionDefinition"),
    "ExtensionManifest": (".plugins", "ExtensionManifest"),
    "RESOURCE_CATALOG_SERVICE": (".resource_packs", "RESOURCE_CATALOG_SERVICE"),
    "ResourceCatalog": (".resource_packs", "ResourceCatalog"),
    "ResourcePackDeclaration": (".resource_packs", "ResourcePackDeclaration"),
    "ToolDeclaration": (".plugins", "ToolDeclaration"),
    "Translator": (".i18n", "Translator"),
    "WorkerOperationBridge": (".operations", "WorkerOperationBridge"),
    "discover_function_host_provider": (".functions", "discover_function_host_provider"),
}


def __getattr__(name: str) -> Any:
    """Load a composition-owned facade export only when requested.

    Args:
        name: Public facade name requested by the importer.

    Returns:
        The imported composition-owned public value.
    """

    try:
        module_name, attribute = _LAZY_EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return eager and lazy public facade names.

    Returns:
        Sorted names available from the branded facade.
    """

    return sorted(set(globals()) | set(_LAZY_EXPORTS))

__all__ = [
    "LiteyukiApp",
    "AuthorizationContext",
    "KERNEL_STATUS_SERVICE",
    "KernelStatusProvider",
    "KernelStatusSnapshot",
    "InitFieldKind",
    "InitFieldSpec",
    "PluginContext",
    "PluginDefinition",
    "ExtensionDefinition",
    "PluginHandle",
    "PluginManifest",
    "ExtensionManifest",
    "PluginInitSpec",
    "PluginPaths",
    "PluginServices",
    "ToolDeclaration",
    "ServiceKey",
    "ServiceRegistry",
    "ServiceRequirement",
    "AGENT_FUNCTION_CATALOG",
    "AGENT_PROMPT_CATALOG",
    "AGENT_PROMPT_SELECT",
    "FUNCTION_DISPATCH_SERVICE",
    "FUNCTION_HOST_ENTRY_POINT_GROUP",
    "FUNCTION_LIBRARY_ENTRY_POINT_GROUP",
    "FunctionCall",
    "FunctionDispatcher",
    "FunctionEventContribution",
    "FunctionHost",
    "FunctionHostBindings",
    "FunctionHostProvider",
    "FunctionPackSource",
    "FunctionPreflight",
    "FunctionPromptPreset",
    "discover_function_host_provider",
    "I18N_SERVICE",
    "MANAGEMENT_SERVICE",
    "ManagementCommand",
    "ManagementRegistry",
    "ManagementPrincipal",
    "OperationConfirmation",
    "OperationDefinition",
    "OperationImpact",
    "OperationLedger",
    "OperationRequest",
    "OperationState",
    "RESOURCE_CATALOG_SERVICE",
    "ResourceCatalog",
    "ResourcePackDeclaration",
    "RuntimeApiBackend",
    "BotSnapshot",
    "EventSnapshot",
    "RuntimeApiError",
    "RuntimeApiProxy",
    "RuntimeBinding",
    "RuntimeCallContext",
    "RuntimeNamespaceProxy",
    "RuntimeRequirement",
    "RuntimeUnavailable",
    "SendResult",
    "create_runtime_proxy",
    "invoke_with_runtime",
    "runtime",
    "runtime_bindings",
    "runtime_handler",
    "validate_runtime_bindings",
    "Translator",
    "WorkerOperationBridge",
    "__version__",
]
