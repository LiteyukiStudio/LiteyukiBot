from __future__ import annotations

import json
from pathlib import Path

import pytest

from liteyukibot.cli import main
from liteyukibot.plugin_sources import OFFICIAL_SOURCE_ID, PluginSource, PluginSourceStore
from liteyukibot.plugin_store import PluginStoreError


def test_source_store_keeps_official_source_and_orders_custom_sources(tmp_path: Path) -> None:
    store = PluginSourceStore(tmp_path)
    store.add(PluginSource("secondary", "https://example.invalid/secondary.json", 20))
    store.add(PluginSource("primary", "https://example.invalid/primary.json", 10))

    assert [source.id for source in store.list()] == [OFFICIAL_SOURCE_ID, "primary", "secondary"]
    assert json.loads((tmp_path / ".liteyuki" / "plugin-sources.json").read_text(encoding="utf-8"))["schema"] == 1


def test_source_store_rejects_reserved_or_insecure_sources(tmp_path: Path) -> None:
    store = PluginSourceStore(tmp_path)

    with pytest.raises(PluginStoreError, match="reserved"):
        store.add(PluginSource(OFFICIAL_SOURCE_ID, "https://example.invalid/index.json"))
    with pytest.raises(PluginStoreError, match="HTTPS"):
        PluginSource("insecure", "http://example.invalid/index.json")


def test_source_cli_manages_workspace_owned_configuration(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            ["--workspace", str(tmp_path), "plugin", "source", "add", "local", "https://example.invalid/index.json"]
        )
        == 0
    )
    assert main(["--workspace", str(tmp_path), "plugin", "source", "list"]) == 0
    output = capsys.readouterr().out
    assert "added local" in output
    assert "local\t100\thttps://example.invalid/index.json" in output

    assert main(["--workspace", str(tmp_path), "plugin", "source", "remove", "local"]) == 0
    assert "removed local" in capsys.readouterr().out
