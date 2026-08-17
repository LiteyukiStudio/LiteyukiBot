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

from ..config.models import AppSettings, BrokerBridgeSettings
from ..config.vault import SecretVault
from ..lyip import LyipFrame
from .peer import BridgeRegistrationError, BrokerPeerServer, BrokerPeerService
from .protocol import (
    ActionResourceDeclaration,
    BridgeAccess,
    BridgeManifest,
    BridgeRegister,
    BridgeRejected,
)


class BridgeLauncher(Protocol):
    """An installed bridge package's process-local launch entry point."""

    def __call__(self, settings: AppSettings, bridge_id: str, token: str) -> Awaitable[None] | None: ...


class BridgeSupportGrade(StrEnum):
    """Release qualification declared by an installed bridge distribution."""

    EXPERIMENTAL = "experimental"
    STABLE = "stable"


@dataclass(frozen=True, slots=True)
class BridgeDefinition:
    """Package-owned metadata and launcher for one bridge kind."""

    kind: str
    grade: BridgeSupportGrade
    distribution: str
    launch: BridgeLauncher


class BridgeCatalog:
    """Discover validated bridge definitions without importing framework packages eagerly."""

    ENTRY_POINT_GROUP = "liteyukibot.bridges"

    def discover(self) -> Mapping[str, BridgeDefinition]:
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

    async def launch(self, settings: AppSettings, bridge_id: str, token: str) -> None:
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
    """Return an entry point's owning distribution when metadata exposes it."""

    distribution = getattr(entry, "dist", None)
    if distribution is None:
        return None
    name = distribution.metadata.get("Name")
    return name if isinstance(name, str) and name else None


def _canonical_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


class _AuthoritativePeerService(BrokerPeerService):
    def __init__(
        self,
        *,
        manifests: Mapping[str, BridgeManifest],
        instance_tokens: Mapping[str, str],
        generation: int,
        active_capacity: int,
        terminal_capacity: int,
        terminal_ttl_seconds: float,
        delivery_timeout_seconds: float,
        diagnostics_token: str | None = None,
    ) -> None:
        super().__init__(
            instance_tokens=instance_tokens,
            generation=generation,
            active_capacity=active_capacity,
            terminal_capacity=terminal_capacity,
            terminal_ttl_seconds=terminal_ttl_seconds,
            delivery_timeout_seconds=delivery_timeout_seconds,
            diagnostics_token=diagnostics_token,
        )
        self._manifests = dict(manifests)

    def _register(self, peer_identity: bytes, frame: LyipFrame, message: BridgeRegister) -> LyipFrame:
        expected = self._manifests.get(message.bridge_id)
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
    ) -> None:
        if set(instance_tokens) != set(settings.broker.bridges):
            raise ValueError("broker tokens must resolve every configured bridge exactly once")
        manifests = {
            bridge_id: BridgeManifest(
                bridge_id=bridge_id,
                access=BridgeAccess(bridge.access),
                subscriptions=bridge.subscriptions,
                action_resources=tuple(
                    ActionResourceDeclaration(kind=item.kind, resource_prefix=item.resource_prefix)
                    for item in bridge.action_resources
                ),
            )
            for bridge_id, bridge in settings.broker.bridges.items()
        }
        self._context = zmq.asyncio.Context.instance()
        self.server = BrokerPeerServer(
            context=self._context,
            endpoint=settings.broker.endpoint,
            generation=settings.broker.generation,
            instance_tokens=instance_tokens,
            active_capacity=settings.broker.active_capacity,
            terminal_capacity=settings.broker.terminal_capacity,
            terminal_ttl_seconds=settings.broker.terminal_ttl_seconds,
            delivery_timeout_seconds=settings.broker.delivery_timeout_seconds,
            diagnostics_token=diagnostics_token,
        )
        self.server.service = _AuthoritativePeerService(
            manifests=manifests,
            instance_tokens=instance_tokens,
            generation=settings.broker.generation,
            active_capacity=settings.broker.active_capacity,
            terminal_capacity=settings.broker.terminal_capacity,
            terminal_ttl_seconds=settings.broker.terminal_ttl_seconds,
            delivery_timeout_seconds=settings.broker.delivery_timeout_seconds,
            diagnostics_token=diagnostics_token,
        )

    @classmethod
    def from_vault(cls, settings: AppSettings, vault: SecretVault, password: str) -> BrokerService:
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
        return cls(settings, tokens, diagnostics_token=diagnostics_token)

    async def run_until_cancelled(self) -> None:
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
        while True:
            try:
                await self.server.serve_control_once()
            except BridgeRegistrationError:
                continue

    async def _serve_business(self) -> None:
        while True:
            try:
                await self.server.serve_business_once()
            except BridgeRegistrationError:
                continue


def bridge_token_from_vault(
    settings: AppSettings, bridge_id: str, vault: SecretVault, password: str
) -> tuple[BrokerBridgeSettings, str]:
    bridge = settings.broker.bridges.get(bridge_id)
    if bridge is None:
        raise RuntimeError(f"broker bridge {bridge_id!r} is not configured")
    token = vault.read(password).get(bridge.token_secret)
    if token is None:
        raise BridgeRegistrationError(
            f"configured broker bridge {bridge_id!r} references a secret that is absent from the vault"
        )
    return bridge, token


__all__ = [
    "BridgeCatalog",
    "BridgeDefinition",
    "BridgeLauncher",
    "BridgeSupportGrade",
    "BrokerService",
    "bridge_token_from_vault",
]
