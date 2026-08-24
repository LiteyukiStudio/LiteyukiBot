from __future__ import annotations

from liteyukibot_webui import resource_pack_declarations, static_assets

from liteyukibot.i18n import Translator
from liteyukibot.resource_packs import ResourceCatalog


def test_static_assets_directory_is_packaged() -> None:
    assert static_assets().is_dir()


def test_webui_resource_pack_is_declared_and_contains_presentation_messages() -> None:
    catalog = ResourceCatalog.load(".", plugin_packs=resource_pack_declarations())
    translator, warning = Translator.from_resources(catalog, "zh-CN")

    assert warning in {None, "Chinese terminal font support was not detected"}
    assert translator.text("webui.nav.events_short") == "事件"
    assert translator.text("webui.events.summary") == "事件摘要"
