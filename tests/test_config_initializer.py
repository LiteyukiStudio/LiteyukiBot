from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from liteyukibot.config import ConfigWorkspace, load_settings
from liteyukibot.config.initializer import build_initialization_plan
from liteyukibot.init_specs import InitFieldKind, InitFieldSpec, PluginInitSpec
from liteyukibot.plugins import PluginContext, PluginDefinition, PluginManager, PluginManifest
from liteyukibot.resource_packs import ResourcePackDeclaration
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
    resource_packs: tuple[ResourcePackDeclaration, ...] = (),
) -> PluginDefinition:
    return PluginDefinition(
        manifest=PluginManifest(
            id=plugin_id,
            name=plugin_id,
            version="1.0.0",
            provides=provides,
            requires=requires,
            resource_packs=resource_packs,
        ),
        setup=_setup,
        init_spec=PluginInitSpec(fields=fields),
    )


def test_initializer_selects_plugin_dependencies_without_legacy_runtimes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    monkeypatch.setattr(
        PluginManager,
        "discover_installed",
        classmethod(lambda _cls: (definitions, ("plugin 'broken' is unavailable",))),
    )

    def prompt(label: str, default: str) -> str:
        return "y" if label.startswith("Enable plugin consumer") else default

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
    assert plan.runtimes == {}
    assert plan.runtime_event_routes == ()
    assert plan.secrets == {}
    assert output == ["warning: plugin 'broken' is unavailable"]

def test_initializer_rejects_unavailable_required_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    definitions = {
        "consumer": _plugin("consumer", requires=(ServiceRequirement(_SERVICE),)),
    }
    monkeypatch.setattr(PluginManager, "discover_installed", classmethod(lambda _cls: (definitions, ())))

    def prompt(label: str, default: str) -> str:
        return "y" if label.startswith("Enable plugin") else default

    with pytest.raises(ValueError, match="unavailable service"):
        build_initialization_plan(prompt=prompt, output=lambda _message: None)


@pytest.mark.skipif(
    importlib.util.find_spec("liteyukibot_essentials") is None,
    reason="essentials package is not installed",
)
def test_initializer_uses_locale_for_kernel_and_package_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    definitions = {
        "consumer": _plugin(
            "consumer",
            fields=(
                InitFieldSpec(
                    key="language",
                    label="Language",
                    label_key="essentials.init.language",
                    kind=InitFieldKind.STRING,
                    default="zh-CN",
                ),
            ),
            resource_packs=(ResourcePackDeclaration("liteyukibot_essentials"),),
        ),
    }
    monkeypatch.setattr(PluginManager, "discover_installed", classmethod(lambda _cls: (definitions, ())))
    prompts: list[str] = []

    def prompt(label: str, default: str) -> str:
        prompts.append(label)
        return "y" if label.startswith("启用插件") else default

    plan = build_initialization_plan(prompt=prompt, output=lambda _message: None, locale="zh-CN")

    assert plan.plugins == ("consumer",)
    assert plan.plugin_config["consumer"] == {"language": "zh-CN"}
    assert prompts[:5] == [
        "数据目录",
        "缓存目录",
        "日志级别",
        "启用控制台日志 [Y/n]",
        "启用 JSON Lines 日志 [y/N]",
    ]
    assert "Plugin consumer: 默认语言" in prompts
