from __future__ import annotations

from pathlib import Path

import pytest

from liteyukibot.config import ConfigWorkspace, load_settings
from liteyukibot.config.initializer import build_initialization_plan
from liteyukibot.init_specs import InitFieldKind, InitFieldSpec, PluginInitSpec, RuntimeInitSpec
from liteyukibot.plugins import PluginContext, PluginDefinition, PluginManager, PluginManifest
from liteyukibot.runtime import RuntimeCatalog, RuntimePlugin
from liteyukibot.services import ServiceKey, ServiceRequirement

_SERVICE = ServiceKey("test.service", 1)


async def _setup(_context: PluginContext) -> None:
    return None


def _plugin(
    plugin_id: str,
    *,
    provides: tuple[ServiceKey, ...] = (),
    requires: tuple[ServiceRequirement, ...] = (),
    fields: tuple[InitFieldSpec, ...] = (),
) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id=plugin_id,
            name=plugin_id,
            version="1.0.0",
            provides=provides,
            requires=requires,
        ),
        setup=_setup,
        init_spec=PluginInitSpec(fields=fields),
    )


def test_initializer_selects_dependencies_and_runtime_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    definitions = {
        "provider": _plugin("provider", provides=(_SERVICE,)),
        "consumer": _plugin(
            "consumer",
            requires=(ServiceRequirement(_SERVICE),),
            fields=(
                InitFieldSpec(
                    key="language",
                    label="Language",
                    kind=InitFieldKind.STRING,
                    default="en",
                ),
            ),
        ),
    }
    runtimes = {
        "source": RuntimePlugin(
            kind="source",
            command=("source",),
            init_spec=RuntimeInitSpec(default_id="source"),
        ),
        "agent": RuntimePlugin(
            kind="agent",
            command=("agent",),
            agent_harness="native",
            init_spec=RuntimeInitSpec(default_id="agent"),
        ),
        "secure": RuntimePlugin(
            kind="secure",
            command=("secure",),
            init_spec=RuntimeInitSpec(
                default_id="secure",
                fields=(
                    InitFieldSpec(
                        key="token",
                        label="Token",
                        kind=InitFieldKind.SECRET,
                        secret_environment="TEST_TOKEN",
                    ),
                ),
            ),
        ),
    }
    monkeypatch.setattr(
        PluginManager,
        "discover_installed",
        classmethod(lambda _cls: (definitions, ("plugin 'broken' is unavailable",))),
    )
    monkeypatch.setattr(
        RuntimeCatalog,
        "discover_installed",
        lambda _self: (runtimes, ("runtime 'broken' is unavailable",)),
    )

    def prompt(label: str, default: str) -> str:
        if label.startswith("Enable plugin consumer"):
            return "y"
        if label.startswith("Enable runtime source"):
            return "y"
        if label.startswith("Enable runtime agent"):
            return "y"
        if label.startswith("Route messages from source"):
            return "y"
        return default

    output: list[str] = []
    plan = build_initialization_plan(prompt=prompt, output=output.append)
    path = ConfigWorkspace(tmp_path).initialize(
        data_dir=plan.data_dir,
        cache_dir=plan.cache_dir,
        logging_level=plan.logging_level,
        payload_mode=plan.payload_mode,
        payload_exclude_runtimes=plan.payload_exclude_runtimes,
        plugins=plan.plugins,
        plugin_config=plan.plugin_config,
        runtimes=plan.runtimes,
        runtime_event_routes=plan.runtime_event_routes,
    )

    settings = load_settings(path, environ={})
    assert plan.plugins == ("provider", "consumer")
    assert settings.plugins.config["consumer"]["language"] == "en"
    assert set(settings.runtimes) == {"source", "agent"}
    assert settings.runtime_event_routes[0].target == "agent"
    assert any("secure vault" in item for item in output)


def test_initializer_rejects_unavailable_required_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    definitions = {
        "consumer": _plugin("consumer", requires=(ServiceRequirement(_SERVICE),)),
    }
    monkeypatch.setattr(PluginManager, "discover_installed", classmethod(lambda _cls: (definitions, ())))
    monkeypatch.setattr(RuntimeCatalog, "discover_installed", lambda _self: ({}, ()))

    def prompt(label: str, default: str) -> str:
        return "y" if label.startswith("Enable plugin") else default

    with pytest.raises(ValueError, match="unavailable service"):
        build_initialization_plan(prompt=prompt, output=lambda _message: None)
