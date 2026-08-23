"""Standalone configuration-authoritative broker service."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib import metadata
from inspect import isawaitable, iscoroutinefunction
from typing import Protocol, cast

import zmq.asyncio

from ..config.models import AppSettings, BrokerBridgeSettings, JsonValue
from ..config.vault import SecretVault
from ..lyip import LyipFrame
from ..runtime.facets import RuntimeFacetInstaller
from .peer import BridgeRegistrationError, BrokerPeerServer, BrokerPeerService
from .protocol import (
    ActionResourceDeclaration,
    BridgeAccess,
    BridgeManifest,
    BridgeRegister,
    BridgeRejected,
    BrokerToolDeclaration,
)


class BridgeLauncher(Protocol):
    """An installed bridge package's process-local launch entry point."""

    def __call__(self, settings: AppSettings, bridge_id: str, token: str) -> Awaitable[None] | None:
        """Invoke the bridge launcher as a callable.

        Args:
            settings: Validated application settings.
            bridge_id: Stable identifier for the bridge.
            token: Authentication token presented at the boundary.

        Returns:
            The `Awaitable[None] | None` result produced by the operation.
        """
        ...


class BridgeSupportGrade(StrEnum):
    """Release qualification declared by an installed bridge distribution."""

    EXPERIMENTAL = "experimental"
    STABLE = "stable"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class BridgeDefinition:
    """Package-owned metadata and launcher for one bridge kind."""

    kind: str
    grade: BridgeSupportGrade
    distribution: str
    launch: BridgeLauncher
    facet_installer: RuntimeFacetInstaller | None = None
    probe_module: str | None = None


class BridgeCatalog:
    """Discover validated bridge definitions without importing framework packages eagerly."""

    ENTRY_POINT_GROUP = "liteyukibot.bridges"

    def discover(self) -> Mapping[str, BridgeDefinition]:
        """Discover the bridge catalog operation.

        Returns:
            The `Mapping[str, BridgeDefinition]` result produced by the operation.
        """
        installed: dict[str, BridgeDefinition] = {}
        for entry in metadata.entry_points(group=self.ENTRY_POINT_GROUP):
            loaded = entry.load()
            if not callable(loaded):
                raise RuntimeError(f"bridge entry point {entry.name!r} must be a definition factory")
            definition = loaded()
            if not isinstance(definition, BridgeDefinition):
                raise RuntimeError(f"bridge entry point {entry.name!r} did not return BridgeDefinition")
            self._validate_definition(entry.name, definition, entry_distribution_name(entry))
            if definition.kind in installed:
                raise RuntimeError(f"bridge entry point {entry.name!r} is duplicated")
            installed[definition.kind] = definition
        return installed

    @staticmethod
    def _validate_definition(
        entry_name: str, definition: BridgeDefinition, entry_distribution: str | None
    ) -> None:
        """Validate definition.

        Args:
            entry_name: The entry name value used by the operation.
            definition: The definition value used by the operation.
            entry_distribution: The entry distribution value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `BridgeCatalog._validate_definition`. It delegates to
            `strip`, `_canonical_distribution_name`, `callable` while keeping intermediate state local to
            the owning operation.
        """
        if not definition.kind or definition.kind != definition.kind.strip():
            raise RuntimeError(f"bridge entry point {entry_name!r} has an invalid kind")
        if definition.kind != entry_name:
            raise RuntimeError(
                f"bridge entry point {entry_name!r} returned the mismatched bridge kind {definition.kind!r}"
            )
        if not definition.distribution or definition.distribution != definition.distribution.strip():
            raise RuntimeError(f"bridge entry point {entry_name!r} has an invalid distribution")
        declared_distribution = _canonical_distribution_name(definition.distribution)
        installed_distribution = (
            _canonical_distribution_name(entry_distribution) if entry_distribution is not None else None
        )
        if installed_distribution is not None and declared_distribution != installed_distribution:
            raise RuntimeError(
                f"bridge entry point {entry_name!r} declares distribution {definition.distribution!r}, "
                f"but is installed by {entry_distribution!r}"
            )
        if not isinstance(definition.grade, BridgeSupportGrade):
            raise RuntimeError(f"bridge entry point {entry_name!r} has an invalid support grade")
        if not callable(definition.launch):
            raise RuntimeError(f"bridge entry point {entry_name!r} has a non-callable launcher")
        if (definition.facet_installer is None) != (definition.probe_module is None):
            raise RuntimeError(
                f"bridge entry point {entry_name!r} must declare both a facet installer and probe module"
            )
        if definition.probe_module is not None and (
            not definition.probe_module or definition.probe_module != definition.probe_module.strip()
        ):
            raise RuntimeError(f"bridge entry point {entry_name!r} has an invalid probe module")

    async def launch(self, settings: AppSettings, bridge_id: str, token: str) -> None:
        """Launch the bridge catalog operation.

        Args:
            settings: Validated application settings.
            bridge_id: Stable identifier for the bridge.
            token: Authentication token presented at the boundary.

        Returns:
            None.
        """
        bridge = settings.broker.bridges.get(bridge_id)
        if bridge is None:
            raise RuntimeError(f"broker bridge {bridge_id!r} is not configured")
        if bridge.kind == "kernel":
            raise RuntimeError("the reserved kernel bridge starts with liteyuki run, not liteyuki bridge run")
        launcher = self.discover().get(bridge.kind)
        if launcher is None:
            raise RuntimeError(f"broker bridge kind {bridge.kind!r} is not installed")
        if iscoroutinefunction(launcher.launch):
            result = launcher.launch(settings, bridge_id, token)
            if isawaitable(result):
                await result
            return
        sync_launcher = cast(Callable[[AppSettings, str, str], object], launcher.launch)
        thread_call = cast(Callable[..., Awaitable[object]], asyncio.to_thread)
        thread_result = await thread_call(sync_launcher, settings, bridge_id, token)
        if isawaitable(thread_result):
            await thread_result


def entry_distribution_name(entry: metadata.EntryPoint) -> str | None:
    """Return an entry point's owning distribution when metadata exposes it.

    Args:
        entry: The entry value used by the operation.

    Returns:
        The `str | None` result produced by the operation.
    """

    distribution = getattr(entry, "dist", None)
    if distribution is None:
        return None
    name = distribution.metadata.get("Name")
    return name if isinstance(name, str) and name else None


def _canonical_distribution_name(name: str) -> str:
    """Implement the canonical distribution name operation for the component.

    Args:
        name: Stable name used to identify the value.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_canonical_distribution_name`. It delegates to `lower`,
        `sub` while keeping intermediate state local to the owning operation.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


class _AuthoritativePeerService(BrokerPeerService):
    """Represent the authoritative peer service contract."""
    def __init__(
        self,
        *,
        manifests: Mapping[str, BridgeManifest],
        instance_tokens: Mapping[str, str],
        generation: int,
        active_capacity: int,
        terminal_capacity: int,
        terminal_content_bytes_capacity: int = 16 * 1024 * 1024,
        terminal_ttl_seconds: float,
        delivery_timeout_seconds: float,
        diagnostics_token: str | None = None,
        management_token: str | None = None,
        dynamic_manifest_bridge_ids: frozenset[str] = frozenset(),
        dynamic_runtime_api_bridge_ids: frozenset[str] = frozenset(),
        runtime_kinds: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize the authoritative peer service.

        Args:
            manifests: The manifests value used by the operation.
            instance_tokens: The instance tokens value used by the operation.
            generation: Positive protocol or deployment generation.
            active_capacity: Maximum retained active count.
            terminal_capacity: Maximum retained terminal count.
            terminal_content_bytes_capacity: Maximum retained terminal content bytes count.
            terminal_ttl_seconds: Configured terminal ttl duration, in seconds.
            delivery_timeout_seconds: Configured delivery timeout duration, in seconds.
            diagnostics_token: The diagnostics token value used by the operation.
            management_token: The management token value used by the operation.
            dynamic_manifest_bridge_ids: Stable identifiers for the dynamic manifest bridge values.
            dynamic_runtime_api_bridge_ids: Stable identifiers for the dynamic runtime api bridge values.
            runtime_kinds: The runtime kinds value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_AuthoritativePeerService.__init__`. It delegates to
            `__init__`, `super` while keeping intermediate state local to the owning operation.
        """
        super().__init__(
            instance_tokens=instance_tokens,
            generation=generation,
            active_capacity=active_capacity,
            terminal_capacity=terminal_capacity,
            terminal_content_bytes_capacity=terminal_content_bytes_capacity,
            terminal_ttl_seconds=terminal_ttl_seconds,
            delivery_timeout_seconds=delivery_timeout_seconds,
            diagnostics_token=diagnostics_token,
            management_token=management_token,
        )
        self._manifests = dict(manifests)
        self._dynamic_manifest_bridge_ids = dynamic_manifest_bridge_ids
        self._dynamic_runtime_api_bridge_ids = dynamic_runtime_api_bridge_ids
        self._runtime_kinds = dict(runtime_kinds or {})

    def _register(self, peer_identity: bytes, frame: LyipFrame, message: BridgeRegister) -> LyipFrame:
        """Register the authoritative peer service operation.

        Args:
            peer_identity: The peer identity value used by the operation.
            frame: The frame value used by the operation.
            message: Message content associated with the operation.

        Returns:
            The `LyipFrame` result produced by the operation.

        Notes:
            Internal implementation detail for `_AuthoritativePeerService._register`. It delegates to `get`,
            `update`, `any`, `_reply` while keeping intermediate state local to the owning operation.
        """
        expected = self._manifests.get(message.bridge_id)
        if expected is not None:
            updates: dict[str, object] = {}
            if message.bridge_id in self._dynamic_manifest_bridge_ids:
                updates.update(tools=message.manifest.tools, controls=message.manifest.controls)
            if message.bridge_id in self._dynamic_runtime_api_bridge_ids:
                expected_kind = self._runtime_kinds.get(message.bridge_id)
                if expected_kind is not None and any(
                    api.runtime_kind != expected_kind for api in message.manifest.runtime_apis
                ):
                    return self._reply(
                        peer_identity,
                        frame,
                        BridgeRejected(
                            code="runtime_api_kind_mismatch",
                            message="runtime API declarations do not match the configured bridge kind",
                        ),
                    )
                updates["runtime_apis"] = message.manifest.runtime_apis
                updates["runtime_api_fingerprint"] = message.manifest.runtime_api_fingerprint
            if updates:
                expected = expected.model_copy(update=updates)
        if expected is not None and message.manifest != expected:
            return self._reply(
                peer_identity,
                frame,
                BridgeRejected(code="manifest_mismatch", message="bridge manifest does not match configuration"),
            )
        return super()._register(peer_identity, frame, message)


class BrokerService:
    """Run the local broker without owning bridge process lifecycles."""

    def __init__(
        self,
        settings: AppSettings,
        instance_tokens: Mapping[str, str],
        *,
        diagnostics_token: str | None = None,
        management_token: str | None = None,
    ) -> None:
        """Initialize the broker service.

        Args:
            settings: Validated application settings.
            instance_tokens: The instance tokens value used by the operation.
            diagnostics_token: The diagnostics token value used by the operation.
            management_token: The management token value used by the operation.

        Returns:
            None.
        """
        if set(instance_tokens) != set(settings.broker.bridges):
            raise ValueError("broker tokens must resolve every configured bridge exactly once")
        manifests = {
            bridge_id: BridgeManifest(
                bridge_id=bridge_id,
                access=BridgeAccess(bridge.access),
                subscriptions=bridge.subscriptions,
                controls=bridge.controls,
                tools=tuple(
                    BrokerToolDeclaration(
                        id=tool.id,
                        description=tool.description,
                        input_schema=tool.input_schema,
                        output_schema=tool.output_schema,
                        capabilities=tool.capabilities,
                    )
                    for tool in bridge.tools
                ),
                action_resources=tuple(
                    ActionResourceDeclaration(
                        kind=item.kind,
                        resource=item.resource,
                        resource_prefix=item.resource_prefix,
                    )
                    for item in bridge.action_resources
                ),
            )
            for bridge_id, bridge in settings.broker.bridges.items()
        }
        dynamic_manifest_bridge_ids = frozenset(
            bridge_id for bridge_id, bridge in settings.broker.bridges.items() if bridge.kind == "kernel"
        )
        dynamic_runtime_api_bridge_ids = frozenset(
            bridge_id for bridge_id, bridge in settings.broker.bridges.items() if bridge.kind != "kernel"
        )
        self._context = zmq.asyncio.Context.instance()
        self.server = BrokerPeerServer(
            context=self._context,
            endpoint=settings.broker.endpoint,
            generation=settings.broker.generation,
            instance_tokens=instance_tokens,
            active_capacity=settings.broker.active_capacity,
            terminal_capacity=settings.broker.terminal_capacity,
            terminal_content_bytes_capacity=settings.broker.terminal_content_bytes_capacity,
            terminal_ttl_seconds=settings.broker.terminal_ttl_seconds,
            delivery_timeout_seconds=settings.broker.delivery_timeout_seconds,
            diagnostics_token=diagnostics_token,
            management_token=management_token,
        )
        self.server.service = _AuthoritativePeerService(
            manifests=manifests,
            instance_tokens=instance_tokens,
            generation=settings.broker.generation,
            active_capacity=settings.broker.active_capacity,
            terminal_capacity=settings.broker.terminal_capacity,
            terminal_content_bytes_capacity=settings.broker.terminal_content_bytes_capacity,
            terminal_ttl_seconds=settings.broker.terminal_ttl_seconds,
            delivery_timeout_seconds=settings.broker.delivery_timeout_seconds,
            diagnostics_token=diagnostics_token,
            management_token=management_token,
            dynamic_manifest_bridge_ids=dynamic_manifest_bridge_ids,
            dynamic_runtime_api_bridge_ids=dynamic_runtime_api_bridge_ids,
            runtime_kinds={bridge_id: bridge.kind for bridge_id, bridge in settings.broker.bridges.items()},
        )

    @classmethod
    def from_vault(cls, settings: AppSettings, vault: SecretVault, password: str) -> BrokerService:
        """Create the broker service from vault.

        Args:
            settings: Validated application settings.
            vault: The vault value used by the operation.
            password: The password value used by the operation.

        Returns:
            The `BrokerService` result produced by the operation.
        """
        values = vault.read(password)
        tokens: dict[str, str] = {}
        for bridge_id, bridge in settings.broker.bridges.items():
            token = values.get(bridge.token_secret)
            if token is None:
                raise BridgeRegistrationError(
                    f"configured broker bridge {bridge_id!r} references a secret that is absent from the vault"
                )
            tokens[bridge_id] = token
        diagnostics_token = None
        if (secret_name := settings.broker.diagnostics_token_secret) is not None:
            diagnostics_token = values.get(secret_name)
            if diagnostics_token is None:
                raise BridgeRegistrationError("broker diagnostics references a secret that is absent from the vault")
        management_token = None
        if (secret_name := settings.broker.management_token_secret) is not None:
            management_token = values.get(secret_name)
            if management_token is None:
                raise BridgeRegistrationError("broker management references a secret that is absent from the vault")
        return cls(settings, tokens, diagnostics_token=diagnostics_token, management_token=management_token)

    async def run_until_cancelled(self) -> None:
        """Run until cancelled.

        Returns:
            None.
        """
        control = asyncio.create_task(self._serve_control(), name="liteyuki-broker-control")
        business = asyncio.create_task(self._serve_business(), name="liteyuki-broker-business")
        try:
            await asyncio.gather(control, business)
        finally:
            control.cancel()
            business.cancel()
            await asyncio.gather(control, business, return_exceptions=True)
            self.server.close()

    async def _serve_control(self) -> None:
        """Serve control.

        Returns:
            None.

        Notes:
            Internal implementation detail for `BrokerService._serve_control`. It delegates to
            `serve_control_once` while keeping intermediate state local to the owning operation.
        """
        while True:
            try:
                await self.server.serve_control_once()
            except BridgeRegistrationError:
                continue

    async def _serve_business(self) -> None:
        """Serve business.

        Returns:
            None.

        Notes:
            Internal implementation detail for `BrokerService._serve_business`. It delegates to
            `serve_business_once` while keeping intermediate state local to the owning operation.
        """
        while True:
            try:
                await self.server.serve_business_once()
            except BridgeRegistrationError:
                continue


def bridge_token_from_vault(
    settings: AppSettings, bridge_id: str, vault: SecretVault, password: str
) -> tuple[BrokerBridgeSettings, str]:
    """Implement the bridge token from vault operation for the component.

    Args:
        settings: Validated application settings.
        bridge_id: Stable identifier for the bridge.
        vault: The vault value used by the operation.
        password: The password value used by the operation.

    Returns:
        The `tuple[BrokerBridgeSettings, str]` result produced by the operation.
    """
    bridge = settings.broker.bridges.get(bridge_id)
    if bridge is None:
        raise RuntimeError(f"broker bridge {bridge_id!r} is not configured")
    token = vault.read(password).get(bridge.token_secret)
    if token is None:
        raise BridgeRegistrationError(
            f"configured broker bridge {bridge_id!r} references a secret that is absent from the vault"
        )
    return bridge, token


def resolve_secret_references(
    value: JsonValue, secrets: Mapping[str, str], *, path: str = "bridge.options"
) -> JsonValue:
    """Resolve structured vault references without changing persisted settings.

    Args:
        value: Value to validate, transform, or store.
        secrets: The secrets value used by the operation.
        path: Filesystem or logical resource path.

    Returns:
        The requested `JsonValue` value.
    """

    if isinstance(value, Mapping):
        if "secret_ref" in value:
            if set(value) != {"secret_ref"}:
                raise BridgeRegistrationError(f"{path} secret_ref objects cannot contain other fields")
            reference = value["secret_ref"]
            if not isinstance(reference, str) or not reference or reference != reference.strip():
                raise BridgeRegistrationError(f"{path} secret_ref must be a non-empty trimmed name")
            secret = secrets.get(reference)
            if secret is None:
                raise BridgeRegistrationError(f"{path} references a secret that is absent from the vault")
            return secret
        return {
            key: resolve_secret_references(child, secrets, path=f"{path}.{key}")
            for key, child in value.items()
        }
    if isinstance(value, tuple):
        return tuple(
            resolve_secret_references(item, secrets, path=f"{path}[{index}]") for index, item in enumerate(value)
        )
    return value


__all__ = [
    "BridgeCatalog",
    "BridgeDefinition",
    "BridgeLauncher",
    "BridgeSupportGrade",
    "BrokerService",
    "bridge_token_from_vault",
    "resolve_secret_references",
]
