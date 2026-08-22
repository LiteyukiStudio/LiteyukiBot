"""Protocol-only discovery boundary for optional Cordis hosts.

The kernel intentionally owns only this small contract. Implementations live
in independently distributed packages discovered through entry-point metadata.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from importlib import metadata
from typing import TYPE_CHECKING, Protocol, cast

from .config.models import CordisSettings
from .events import EventBus
from .exceptions import PluginError
from .functions import FunctionHost
from .plugins import ExtensionCoexistence, ExtensionIdentity, ToolCallback, ToolDeclaration
from .resource_packs import ResourcePackDeclaration
from .runtime_api import RuntimeContextFactory, RuntimeResolver
from .services import ServiceRegistry

if TYPE_CHECKING:
    from .events import ActionEnvelope, ActionResult, EventEnvelope
    from .logging import Logger


CORDIS_HOST_ENTRY_POINT_GROUP = "liteyukibot.cordis_hosts"


class CordisHost(Protocol):
    """An optional host managed by :class:`LiteyukiApp`."""

    async def start(self) -> None:
        """Start the cordis host.

        Returns:
            None.
        """
        ...

    async def aclose(self) -> None:
        """Close the cordis host asynchronously.

        Returns:
            None.
        """
        ...

    @property
    def plugin_identities(self) -> tuple[ExtensionIdentity, ...]:
        """Return the cordis host's plugin identities.

        Returns:
            The `tuple[ExtensionIdentity, ...]` result produced by the operation.
        """
        ...

    @property
    def plugin_access(self) -> Mapping[str, str]:
        """Return the cordis host's plugin access.

        Returns:
            The `Mapping[str, str]` result produced by the operation.
        """
        ...

    @property
    def tool_declarations(self) -> tuple[ToolDeclaration, ...]:
        """Return the cordis host's tool declarations.

        Returns:
            The `tuple[ToolDeclaration, ...]` result produced by the operation.
        """
        ...

    @property
    def tool_handlers(self) -> Mapping[str, ToolCallback]:
        """Return the cordis host's tool handlers.

        Returns:
            The `Mapping[str, ToolCallback]` result produced by the operation.
        """
        ...

    def bind_function_hosts(self, hosts: Mapping[str, FunctionHost]) -> None:
        """Bind function hosts.

        Args:
            hosts: Function hosts keyed by their stable provider identifiers.

        Returns:
            None.
        """
        ...

    @property
    def runtime_manifests(self) -> Mapping[str, object]:
        """Return the cordis host's runtime manifests.

        Returns:
            The `Mapping[str, object]` result produced by the operation.
        """
        ...

    @property
    def function_resource_packs(self) -> Mapping[str, tuple[ResourcePackDeclaration, ...]]:
        """Return the cordis host's function resource packs.

        Returns:
            The `Mapping[str, tuple[ResourcePackDeclaration, ...]]` result produced by the operation.
        """
        ...


class ActionServiceLike(Protocol):
    """Define the structural interface required from a action service like."""
    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        """Execute one request through the action service like.

        Args:
            action: Action request being processed.
            event: Event associated with the operation.

        Returns:
            The `ActionResult` result produced by the operation.
        """
        ...


CordisHostFactory = Callable[..., CordisHost]


def validate_extension_topology(native: Iterable[ExtensionIdentity], cordis: Iterable[ExtensionIdentity]) -> None:
    """Reject duplicate host activation unless both declarations are infrastructure.

    This validates only startup ownership. Third-party plugins remain responsible
    for their own semantic compatibility with either host.

    Args:
        native: The native value used by the operation.
        cordis: The cordis value used by the operation.

    Returns:
        None.
    """

    native_by_id = _index_identities(native, host="Native")
    cordis_by_id = _index_identities(cordis, host="Cordis")
    for extension_id in sorted(native_by_id.keys() & cordis_by_id.keys()):
        if (
            native_by_id[extension_id].coexistence is ExtensionCoexistence.INFRASTRUCTURE
            and cordis_by_id[extension_id].coexistence is ExtensionCoexistence.INFRASTRUCTURE
        ):
            continue
        raise PluginError(
            f"extension {extension_id!r} is enabled in both Native and Cordis hosts; "
            "both definitions must declare coexistence='infrastructure'"
        )


def _index_identities(identities: Iterable[ExtensionIdentity], *, host: str) -> dict[str, ExtensionIdentity]:
    """Implement the index identities operation for the component.

    Args:
        identities: The identities value used by the operation.
        host: The host value used by the operation.

    Returns:
        The `dict[str, ExtensionIdentity]` result produced by the operation.

    Notes:
        Internal implementation detail for `_index_identities`. It performs the local state transition
        directly and is not a stable extension boundary.
    """
    values: dict[str, ExtensionIdentity] = {}
    for identity in identities:
        if identity.id in values:
            raise PluginError(f"duplicate {host} extension identity: {identity.id}")
        values[identity.id] = identity
    return values


def discover_cordis_host(
    settings: CordisSettings,
    *,
    events: EventBus,
    actions: ActionServiceLike,
    logger: Logger,
    services: ServiceRegistry | None = None,
    data_dir: object | None = None,
    cache_dir: object | None = None,
    runtime_context_factory: Callable[[str], RuntimeContextFactory] | None = None,
    runtime_resolver: RuntimeResolver | None = None,
    runtime_targets: Mapping[str, str] | None = None,
) -> CordisHost | None:
    """Resolve the one configured host without importing optional packages eagerly.

    Args:
        settings: Validated application settings.
        events: The events value used by the operation.
        actions: The actions value used by the operation.
        logger: Structured logger used for diagnostics.
        services: The services value used by the operation.
        data_dir: Filesystem path for the data.
        cache_dir: Filesystem path for the cache.
        runtime_context_factory: The runtime context factory value used by the operation.
        runtime_resolver: The runtime resolver value used by the operation.
        runtime_targets: The runtime targets value used by the operation.

    Returns:
        The `CordisHost | None` result produced by the operation.
    """

    if not settings.enabled:
        return None

    entry_points = tuple(metadata.entry_points(group=CORDIS_HOST_ENTRY_POINT_GROUP))
    if not entry_points:
        raise RuntimeError("Cordis plugins are enabled but no liteyukibot.cordis_hosts implementation is installed")
    if len(entry_points) != 1:
        names = ", ".join(sorted(entry.name for entry in entry_points))
        raise RuntimeError(f"Cordis plugins require exactly one host implementation; found: {names}")

    entry_point = entry_points[0]
    try:
        candidate = entry_point.load()
    except Exception as error:
        raise RuntimeError(f"Cordis host entry point {entry_point.name!r} could not be imported") from error
    if not callable(candidate):
        raise RuntimeError(f"Cordis host entry point {entry_point.name!r} must be callable")

    factory = cast(CordisHostFactory, candidate)
    try:
        factory_kwargs: dict[str, object] = {
            "events": events,
            "actions": actions,
            "settings": settings,
            "logger": logger,
            "runtime_context_factory": runtime_context_factory,
            "runtime_resolver": runtime_resolver,
            "runtime_targets": runtime_targets,
        }
        if services is not None:
            factory_kwargs.update(services=services, data_dir=data_dir, cache_dir=cache_dir)
        try:
            parameters: Mapping[str, inspect.Parameter] = inspect.signature(factory).parameters
        except (TypeError, ValueError):
            parameters = {}
            factory_kwargs = {
                "events": events,
                "actions": actions,
                "settings": settings,
                "logger": logger,
            }
        else:
            if not any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
                factory_kwargs = {name: value for name, value in factory_kwargs.items() if name in parameters}
        host = factory(**factory_kwargs)
    except Exception as error:
        raise RuntimeError(f"Cordis host entry point {entry_point.name!r} could not be created") from error
    if not callable(getattr(host, "start", None)) or not callable(getattr(host, "aclose", None)):
        raise RuntimeError(f"Cordis host entry point {entry_point.name!r} returned an invalid host")
    identities = getattr(host, "plugin_identities", None)
    if not isinstance(identities, tuple) or not all(isinstance(item, ExtensionIdentity) for item in identities):
        raise RuntimeError(f"Cordis host entry point {entry_point.name!r} returned an invalid plugin topology")
    return host


__all__ = [
    "ActionServiceLike",
    "CORDIS_HOST_ENTRY_POINT_GROUP",
    "CordisHost",
    "CordisHostFactory",
    "discover_cordis_host",
    "validate_extension_topology",
]
