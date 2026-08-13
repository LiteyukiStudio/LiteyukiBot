from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

import liteyukibot.cli as cli_module
from liteyukibot.config import inspect_settings, redact_config, toml_compatible_config


def test_inspection_tracks_all_precedence_layers_with_json_pointer(tmp_path: Path) -> None:
    included = tmp_path / "included.toml"
    included.write_text("[core]\nqueue_capacity = 10\n", encoding="utf-8")
    primary = tmp_path / "liteyuki.toml"
    primary.write_text(
        'config_version = 1\ninclude = ["included.toml"]\n[core]\nqueue_capacity = 20\n',
        encoding="utf-8",
    )
    additional = tmp_path / "extra.toml"
    additional.write_text("[core]\nqueue_capacity = 30\n", encoding="utf-8")

    inspection = inspect_settings(
        primary,
        config_paths=(additional,),
        environ={"LITEYUKI__CORE__QUEUE_CAPACITY": "40"},
        cli_overrides=("core.queue_capacity=50",),
    )
    explanation = inspection.explain("/core/queue_capacity")

    assert explanation.value == 50
    assert [source.kind for source in explanation.sources] == [
        "default",
        "file",
        "file",
        "file",
        "environment",
        "command_line",
    ]


def test_inspection_json_pointer_keeps_dotted_plugin_ids_unambiguous(tmp_path: Path) -> None:
    config = tmp_path / "liteyuki.toml"
    config.write_text(
        'config_version = 1\n[plugins.config."example.plugin"]\nvalue = "configured"\n',
        encoding="utf-8",
    )

    inspection = inspect_settings(config, environ={})

    assert inspection.explain("/plugins/config/example.plugin/value").value == "configured"
    with pytest.raises(ValueError, match="RFC 6901"):
        inspection.explain("plugins.config.example.plugin.value")


def test_config_show_and_explain_redact_sensitive_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "liteyuki.toml"
    config.write_text(
        'config_version = 3\n[plugins.config.demo]\napi_key = "live-value"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert cli_module.main(["config", "show"]) == 0
    shown = capsys.readouterr().out
    assert "live-value" not in shown
    assert json.loads(shown)["plugins"]["config"]["demo"]["api_key"] == "<redacted>"

    assert cli_module.main(["config", "show", "--format", "toml"]) == 0
    rendered_toml = capsys.readouterr().out
    assert "live-value" not in rendered_toml
    assert tomllib.loads(rendered_toml)["plugins"]["config"]["demo"]["api_key"] == "<redacted>"

    assert cli_module.main(["--set", "core.queue_capacity=11", "config", "explain", "/core/queue_capacity"]) == 0
    explanation = json.loads(capsys.readouterr().out)
    assert explanation["value"] == 11
    assert explanation["sources"][-1]["kind"] == "command_line"


def test_redaction_descends_into_nested_collections() -> None:
    document = {
        "credentials": {"access_token": "token-value"},
        "safe": [{"value": "visible"}],
    }

    assert redact_config(document) == {
        "credentials": "<redacted>",
        "safe": [{"value": "visible"}],
    }


def test_toml_output_omits_optional_nulls_but_rejects_null_arrays() -> None:
    assert toml_compatible_config({"optional": None, "nested": {"value": 1}}) == {
        "nested": {"value": 1}
    }
    with pytest.raises(ValueError, match="null array"):
        toml_compatible_config({"items": [None]})
