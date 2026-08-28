"""Fixed Alpha15 built-in feature chain."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from liteyukibot_cordis import CordisManager, Scope

from . import commands, essentials, permissions, profile, resources
from .common import LOGGER_PROVIDER, SERVICE_REGISTRY

type FeatureFactory = Callable[[Scope], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    id: str
    factory: FeatureFactory


BUILTIN_FEATURES: tuple[FeatureDefinition, ...] = (
    FeatureDefinition("liteyukibot.permissions", permissions.activate),
    FeatureDefinition("liteyukibot.commands", commands.activate),
    FeatureDefinition("liteyukibot.resources", resources.activate),
    FeatureDefinition("liteyukibot.profile", profile.activate),
    FeatureDefinition("liteyukibot.essentials", essentials.activate),
)


def feature_order() -> tuple[str, ...]:
    return tuple(feature.id for feature in BUILTIN_FEATURES)


async def activate_builtin_features(
    manager: CordisManager,
    *,
    configs: Mapping[str, Mapping[str, object]] | None = None,
    providers: Mapping[object, object] | None = None,
) -> tuple[Scope, ...]:
    configs = {} if configs is None else configs
    unknown = set(configs) - set(feature_order())
    if unknown:
        raise ValueError(f"unknown built-in feature configs: {', '.join(sorted(unknown))}")
    if providers:
        for key, value in providers.items():
            manager.scope.provide(key, _constant_provider(value))

    scopes: list[Scope] = []
    parent: Scope | None = None
    for feature in BUILTIN_FEATURES:
        scope = await manager.activate(
            feature.id,
            feature.factory,
            config=dict(configs.get(feature.id, {})),
            parent=parent,
        )
        scopes.append(scope)
        parent = scope
    return tuple(scopes)


def _constant_provider(value: object) -> Callable[[], object]:
    def provide() -> object:
        return value

    return provide


__all__ = [
    "BUILTIN_FEATURES",
    "LOGGER_PROVIDER",
    "SERVICE_REGISTRY",
    "FeatureDefinition",
    "activate_builtin_features",
    "feature_order",
]
