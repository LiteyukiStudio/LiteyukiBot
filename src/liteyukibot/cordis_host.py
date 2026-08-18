"""Protocol-only discovery boundary for optional Cordis hosts.

The kernel intentionally owns only this small contract. Implementations live
in independently distributed packages discovered through entry-point metadata.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from importlib import metadata
from typing import TYPE_CHECKING, Protocol, cast

from .config.models import CordisSettings
from .events import EventBus
from .exceptions import PluginError
from .plugins import ExtensionCoexistence, ExtensionIdentity, ToolCallback, ToolDeclaration

if TYPE_CHECKING:
    from .events import ActionEnvelope, ActionResult, EventEnvelope
    from .logging import Logger


CORDIS_HOST_ENTRY_POINT_GROUP = "liteyukibot.cordis_hosts"


class CordisHost(Protocol):
    """An optional host managed by :class:`LiteyukiApp`."""

    async def start(self) -> None: ...

    async def aclose(self) -> None: ...

    @property
    def plugin_identities(self) -> tuple[ExtensionIdentity, ...]: ...

    @property
    def plugin_access(self) -> Mapping[str, str]: ...

    @property
    def tool_declarations(self) -> tuple[ToolDeclaration, ...]: ...

    @property
    def tool_handlers(self) -> Mapping[str, ToolCallback]: ...


class ActionServiceLike(Protocol):
    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult: ...


CordisHostFactory = Callable[..., CordisHost]


def validate_extension_topology(native: Iterable[ExtensionIdentity], cordis: Iterable[ExtensionIdentity]) -> None:
    """Reject duplicate host activation unless both declarations are infrastructure.

    This validates only startup ownership. Third-party plugins remain responsible
    for their own semantic compatibility with either host.
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
) -> CordisHost | None:
    """Resolve the one configured host without importing optional packages eagerly."""

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
        host = factory(events=events, actions=actions, settings=settings, logger=logger)
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
