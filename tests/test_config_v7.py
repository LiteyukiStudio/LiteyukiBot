from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from liteyukibot.config import AgentSettings, AppSettings, ConfigurationError, RuntimeSettings, load_settings


def test_defaults_and_result_are_deeply_immutable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    settings = load_settings(environ={})

    assert settings.core.queue_capacity == 1024
    assert settings.core.data_dir == tmp_path / "data"
    with pytest.raises(ValidationError):
        settings.core.queue_capacity = 1
    with pytest.raises(TypeError):
        settings.runtimes["worker"] = settings.runtimes.get("worker")  # type: ignore[index]


def test_file_env_and_cli_precedence_with_source_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    include_directory = tmp_path / "includes"
    include_directory.mkdir()
    additional_directory = tmp_path / "additional"
    additional_directory.mkdir()

    (include_directory / "base.toml").write_text(
        """
[core]
queue_capacity = 10
data_dir = "include-data"

[logging]
file = "logs/runtime.jsonl"

[plugins]
enabled = ["include"]

[plugins.config.demo]
from_include = true
nested = { include = true }
""",
        encoding="utf-8",
    )
    (tmp_path / "primary.toml").write_text(
        """
include = ["includes/base.toml"]

[core]
queue_capacity = 20
data_dir = "primary-data"

[plugins]
enabled = ["primary"]

[plugins.config.demo]
from_primary = true
nested = { primary = true }
""",
        encoding="utf-8",
    )
    (additional_directory / "override.json").write_text(
        """{
  "core": {"queue_capacity": 30},
  "plugins": {"config": {"demo": {"from_additional": true}}},
  "runtimes": {
    "nb": {
      "kind": "nonebot",
      "working_directory": "runtime",
      "max_inbound_events": 7,
      "options": {"adapter": "onebot", "features": ["messages", "notices"]}
    },
    "compat": {
      "kind": "custom",
      "command": ["compat-runtime"]
    }
  },
  "runtime_event_routes": [
    {"sources": ["nb"], "target": "compat", "messages_only": true}
  ]
}""",
        encoding="utf-8",
    )

    settings = load_settings(
        tmp_path / "primary.toml",
        config_paths=[additional_directory / "override.json"],
        environ={"LITEYUKI__CORE__QUEUE_CAPACITY": "40"},
        cli_overrides=["core.queue_capacity=50", 'plugins.enabled=["cli"]'],
    )

    assert settings.core.queue_capacity == 50
    assert settings.core.data_dir == tmp_path / "primary-data"
    assert settings.logging.file == include_directory / "logs/runtime.jsonl"
    assert settings.plugins.enabled == ("cli",)
    assert settings.plugins.config["demo"] == {
        "from_include": True,
        "from_primary": True,
        "from_additional": True,
        "nested": {"include": True, "primary": True},
    }
    assert settings.runtimes["nb"].working_directory == additional_directory / "runtime"
    assert settings.runtimes["nb"].max_inbound_events == 7
    assert settings.runtimes["nb"].options["features"] == ("messages", "notices")
    assert settings.runtime_event_routes[0].sources == ("nb",)
    assert settings.runtime_event_routes[0].target == "compat"
    assert settings.runtime_event_routes[0].messages_only is True
    serialized = settings.model_dump(mode="json")
    assert serialized["runtimes"]["nb"]["options"]["features"] == ["messages", "notices"]
    assert serialized["runtime_event_routes"] == [
        {"sources": ["nb"], "target": "compat", "messages_only": True}
    ]
    with pytest.raises(TypeError):
        settings.plugins.config["demo"]["new"] = True
    with pytest.raises(TypeError):
        settings.runtimes["nb"].options["new"] = True  # type: ignore[index]


def test_runtime_options_reject_non_json_values(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        RuntimeSettings(
            kind="custom",
            command=("runtime",),
            options={"path": tmp_path},  # type: ignore[dict-item]
        )


def test_runtime_rejects_non_positive_inbound_event_capacity() -> None:
    with pytest.raises(ValidationError, match="max_inbound_events"):
        RuntimeSettings(kind="nonebot", max_inbound_events=0)


def test_runtime_accepts_external_kind_with_an_explicit_command() -> None:
    settings = RuntimeSettings(kind="astrbot", command=("astrbot-runtime",))

    assert settings.kind == "astrbot"


def test_agent_harness_must_be_a_trimmed_nonempty_identifier() -> None:
    assert AgentSettings(agent_harness="native").agent_harness == "native"
    with pytest.raises(ValidationError, match="agent_harness"):
        AgentSettings(agent_harness=" native ")


@pytest.mark.parametrize(
    ("routes", "message"),
    (
        (
            ({"sources": ["source"], "target": "missing"},),
            "target 'missing' is not configured",
        ),
        (
            ({"sources": ["source"], "target": "target"},),
            "source 'source' is disabled",
        ),
        (
            (
                {"sources": ["source"], "target": "target"},
                {"sources": ["source"], "target": "target"},
            ),
            "must not contain duplicates",
        ),
    ),
)
def test_runtime_event_routes_require_distinct_enabled_configured_runtimes(
    routes: tuple[dict[str, object], ...], message: str
) -> None:
    runtimes = {
        "source": RuntimeSettings(kind="nonebot", enabled=message != "source 'source' is disabled"),
        "target": RuntimeSettings(kind="custom", command=("runtime",)),
    }

    with pytest.raises(ValidationError, match=message):
        AppSettings(runtimes=runtimes, runtime_event_routes=routes)  # type: ignore[arg-type]


def test_nested_includes_merge_in_declared_order(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "first.json").write_text('{"core": {"queue_capacity": 5, "max_concurrent_events": 8}}', encoding="utf-8")
    (nested / "second.toml").write_text("[core]\nqueue_capacity = 6\n", encoding="utf-8")
    (tmp_path / "primary.toml").write_text(
        'include = ["nested/first.json", "nested/second.toml"]\n[core]\nhandler_timeout_seconds = 12\n',
        encoding="utf-8",
    )

    settings = load_settings(tmp_path / "primary.toml", environ={})

    assert settings.core.queue_capacity == 6
    assert settings.core.max_concurrent_events == 8
    assert settings.core.handler_timeout_seconds == 12


def test_duplicate_and_validation_errors_are_aggregated_without_values(tmp_path: Path) -> None:
    (tmp_path / "included.toml").write_text("[core]\nqueue_capacity = 1\n", encoding="utf-8")
    (tmp_path / "primary.toml").write_text(
        """
include = ["included.toml", "included.toml"]
secret_value = "must-not-appear"

[core]
queue_capacity = 0
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError) as captured:
        load_settings(tmp_path / "primary.toml", environ={})

    message = str(captured.value)
    assert len(captured.value.issues) == 3
    assert "included more than once" in message
    assert "core.queue_capacity" in message
    assert "secret_value" in message
    assert "must-not-appear" not in message


def test_include_cycle_has_the_full_chain(tmp_path: Path) -> None:
    (tmp_path / "a.toml").write_text('include = ["b.toml"]\n', encoding="utf-8")
    (tmp_path / "b.toml").write_text('include = ["a.toml"]\n', encoding="utf-8")

    with pytest.raises(ConfigurationError) as captured:
        load_settings(tmp_path / "a.toml", environ={})

    assert len(captured.value.issues) == 1
    assert "include cycle detected" in str(captured.value)
    assert "a.toml" in str(captured.value)
    assert "b.toml" in str(captured.value)


def test_yaml_support_is_lazy_and_has_an_actionable_missing_extra_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    yaml_path = tmp_path / "settings.yaml"
    yaml_path.write_text("core:\n  queue_capacity: 7\n", encoding="utf-8")
    real_import_module = importlib.import_module

    def fail_yaml_import(name: str) -> object:
        if name == "yaml":
            raise ModuleNotFoundError("No module named 'yaml'", name="yaml")
        return real_import_module(name)

    monkeypatch.setattr(importlib, "import_module", fail_yaml_import)
    with pytest.raises(ConfigurationError, match=r"liteyukibot-v7\[yaml\]"):
        load_settings(yaml_path, environ={})


def test_yaml_uses_safe_load_when_extra_is_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_path = tmp_path / "settings.yaml"
    yaml_path.write_text("core:\n  queue_capacity: 7\n", encoding="utf-8")
    fake_yaml = SimpleNamespace(safe_load=lambda value: {"core": {"queue_capacity": 7}})
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_yaml)

    settings = load_settings(yaml_path, environ={})

    assert settings.core.queue_capacity == 7


def test_http_is_restricted_to_loopback(tmp_path: Path) -> None:
    config_path = tmp_path / "remote.toml"
    config_path.write_text('[http]\nenabled = true\nhost = "0.0.0.0"\n', encoding="utf-8")

    with pytest.raises(ConfigurationError, match="HTTP host must be a loopback address"):
        load_settings(config_path, environ={})

    settings = load_settings(
        config_path,
        environ={"LITEYUKI__HTTP__HOST": '"::1"'},
    )
    assert settings.http.host == "::1"
