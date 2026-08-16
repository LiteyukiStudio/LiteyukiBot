from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import liteyukibot.config.models as config_models
from liteyukibot.config import (
    AgentSettings,
    AppSettings,
    ConfigurationError,
    DevelopmentSettings,
    LyipLinkCapacitySettings,
    LyipLinkSettings,
    LyipNativeDiagnostics,
    LyipSettings,
    RuntimeSettings,
    WebUISettings,
    load_settings,
    lyip_native_diagnostics,
)


def test_defaults_and_result_are_deeply_immutable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    settings = load_settings(environ={})

    assert settings.core.queue_capacity == 1024
    assert settings.core.data_dir == tmp_path / "data"
    with pytest.raises(ValidationError):
        settings.core.queue_capacity = 1
    with pytest.raises(TypeError):
        settings.runtimes["worker"] = settings.runtimes.get("worker")  # type: ignore[index]


def test_primary_configuration_requires_explicit_v5_version(tmp_path: Path) -> None:
    config = tmp_path / "liteyuki.toml"
    config.write_text("[core]\nqueue_capacity = 32\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="requires config_version = 5"):
        load_settings(config, environ={})


def test_primary_config_version_cannot_be_supplied_by_an_include(tmp_path: Path) -> None:
    (tmp_path / "included.toml").write_text("config_version = 5\n", encoding="utf-8")
    primary = tmp_path / "liteyuki.toml"
    primary.write_text('include = ["included.toml"]\n', encoding="utf-8")

    with pytest.raises(ConfigurationError, match="requires config_version = 5"):
        load_settings(primary, environ={})


def test_primary_v3_config_cannot_be_upgraded_by_an_additional_layer(tmp_path: Path) -> None:
    primary = tmp_path / "liteyuki.toml"
    primary.write_text("config_version = 3\n", encoding="utf-8")
    override = tmp_path / "override.toml"
    override.write_text("config_version = 5\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="requires config_version = 5"):
        load_settings(primary, config_paths=(override,), environ={})


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
config_version = 5
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
  "broker": {"generation": 3}
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
    assert settings.broker.generation == 3
    serialized = settings.model_dump(mode="json")
    assert serialized["broker"]["generation"] == 3
    with pytest.raises(TypeError):
        settings.plugins.config["demo"]["new"] = True


def test_runtime_secret_environment_is_immutable_and_serialized() -> None:
    settings = RuntimeSettings(
        kind="agent",
        secret_env={"LITEYUKI_AGENT_API_KEY": "runtime.agent.api_key_secret"},
    )

    assert settings.model_dump(mode="json")["secret_env"] == {
        "LITEYUKI_AGENT_API_KEY": "runtime.agent.api_key_secret"
    }
    with pytest.raises(TypeError):
        settings.secret_env["OTHER"] = "secret"  # type: ignore[index]


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


def test_v5_lyip_webui_and_development_settings_are_typed_and_serialized() -> None:
    settings = AppSettings(
        lyip=LyipSettings(
            default_backend="zmq",
            capacity_profile="throughput",
            links={
                "worker": LyipLinkSettings(
                    backend="shm",
                    capacity=LyipLinkCapacitySettings(
                        business_slots=1_024, control_slots=64, blob_arena_mib=8, zmq_hwm=1_024
                    ),
                )
            },
        ),
        webui=WebUISettings(mode="always", port=0, session_idle_seconds=60, session_max_seconds=300),
        development=DevelopmentSettings(enabled=True, allow_drills=True),
    )

    assert settings.config_version == 5
    assert settings.lyip.default_backend == "zmq"
    assert settings.lyip.links["worker"].capacity.business_slots == 1_024
    assert settings.webui.mode == "always"
    assert settings.development.allow_drills is True
    assert settings.model_dump(mode="json")["lyip"]["links"]["worker"]["backend"] == "shm"
    with pytest.raises(TypeError):
        settings.lyip.links["other"] = settings.lyip.links["worker"]  # type: ignore[index]


@pytest.mark.parametrize(
    ("factory", "message"),
    (
        (lambda: LyipSettings(links={" worker": LyipLinkSettings()}), "LYIP link runtime identifiers"),
        (lambda: WebUISettings(session_idle_seconds=61, session_max_seconds=60), "session_max_seconds"),
        (lambda: DevelopmentSettings.model_validate({"dev_mode": True}), "dev_mode"),
        (lambda: AppSettings(config_version=3), "config_version must be 5"),
    ),
)
def test_v5_settings_reject_invalid_or_legacy_fields(factory: object, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    ("capacity", "message"),
    (
        (LyipLinkCapacitySettings(business_slots=256, control_slots=32, blob_arena_mib=4, zmq_hwm=256), None),
        ({"business_slots": 512}, "must provide all four"),
        ({"business_slots": 300, "control_slots": 32, "blob_arena_mib": 4, "zmq_hwm": 256}, "power of two"),
        ({"business_slots": 128, "control_slots": 32, "blob_arena_mib": 4, "zmq_hwm": 256}, "between 256 and 65536"),
        ({"business_slots": 256, "control_slots": 16, "blob_arena_mib": 4, "zmq_hwm": 256}, "between 32 and 4096"),
        ({"business_slots": 256, "control_slots": 32, "blob_arena_mib": 2, "zmq_hwm": 256}, "between 4 and 512"),
        ({"business_slots": 256, "control_slots": 32, "blob_arena_mib": 4, "zmq_hwm": 128}, "between 256 and 65536"),
    ),
)
def test_lyip_capacity_override_requires_all_power_of_two_limits(
    capacity: LyipLinkCapacitySettings | dict[str, int], message: str | None
) -> None:
    if message is None:
        assert capacity.business_slots == 256  # type: ignore[union-attr]
        return
    with pytest.raises(ValidationError, match=message):
        LyipLinkCapacitySettings.model_validate(capacity)


def test_lyip_link_resolution_inherits_profile_or_uses_complete_override() -> None:
    settings = LyipSettings(
        default_backend="auto",
        capacity_profile="latency",
        links={
            "inherited": LyipLinkSettings(),
            "custom": LyipLinkSettings(
                backend="zmq",
                capacity_profile="throughput",
                capacity=LyipLinkCapacitySettings(
                    business_slots=8_192,
                    control_slots=1_024,
                    blob_arena_mib=64,
                    zmq_hwm=8_192,
                ),
            ),
        },
    )

    inherited = settings.resolve_link("inherited")
    missing = settings.resolve_link("missing")
    custom = settings.resolve_link("custom")

    assert inherited.backend == "auto"
    assert inherited.capacity_profile == "latency"
    assert inherited.capacity.business_slots == 1_024
    assert missing.capacity.blob_arena_mib == 8
    assert custom.backend == "zmq"
    assert custom.capacity_profile == "throughput"
    assert custom.capacity.control_slots == 1_024


def test_native_diagnostics_are_derived_and_require_an_explanation(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_native(_name: str) -> object:
        raise ImportError

    monkeypatch.setattr(config_models, "import_module", missing_native)
    absent = lyip_native_diagnostics()
    assert absent.state == "unavailable"
    assert absent.wheel_version is None
    assert absent.fallback_reason is not None
    assert "not installed" in absent.fallback_reason

    monkeypatch.setattr(
        config_models,
        "import_module",
        lambda _name: SimpleNamespace(LYIP_NATIVE_ABI=1, native_available=False),
    )
    monkeypatch.setattr("liteyukibot.config.models.metadata.version", lambda _name: "0.1.0b3")
    fallback = lyip_native_diagnostics()
    assert fallback.model_dump(mode="json") == {
        "state": "unavailable",
        "wheel_version": "0.1.0b3",
        "abi": 1,
        "platform": fallback.platform,
        "fallback_reason": "the native wheel has no usable shared-memory transport",
    }
    with pytest.raises(ValidationError, match="fallback reason"):
        LyipNativeDiagnostics(state="unavailable", platform="test")


@pytest.mark.parametrize(
    ("factory", "message"),
    (
        (lambda: LyipSettings(terminal_capacity=1_023), "greater than or equal to 1024"),
        (lambda: LyipSettings(terminal_capacity=262_145), "less than or equal to 262144"),
        (lambda: LyipSettings(terminal_ttl_seconds=59), "greater than or equal to 60"),
        (lambda: LyipSettings(dev_summary_ttl_seconds=3_601), "less than or equal to 3600"),
        (lambda: WebUISettings.model_validate({"mode": "always_on"}), "Input should be"),
        (lambda: WebUISettings(idle_shutdown_seconds=29), "greater than or equal to 30"),
        (lambda: WebUISettings(ticket_ttl_seconds=14), "greater than or equal to 15"),
        (lambda: WebUISettings(session_idle_seconds=14_401), "less than or equal to 14400"),
        (lambda: WebUISettings(session_max_seconds=299), "greater than or equal to 300"),
    ),
)
def test_v4_lyip_and_webui_ranges_are_exact(factory: object, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    ("factory", "message"),
    (
        (lambda: AppSettings(development=DevelopmentSettings(allow_drills=True)), "allow_drills requires"),
        (lambda: AppSettings(development=DevelopmentSettings(watch_auto_restart=True)), "watch_auto_restart requires"),
        (
            lambda: AppSettings(logging={"payload_mode": "full"}),  # type: ignore[arg-type]
            "payload_mode=full requires development.enabled",
        ),
        (
            lambda: AppSettings(logging={"payload_mode": "metadata", "payload_exclude_runtimes": ["worker"]}),  # type: ignore[arg-type]
            "payload_exclude_runtimes requires",
        ),
    ),
)
def test_v4_cross_section_development_and_logging_policies(factory: object, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        factory()  # type: ignore[operator]


def test_full_payload_logging_requires_development_private_file_and_safe_outputs(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    valid = AppSettings(
        core={"data_dir": data_dir},  # type: ignore[arg-type]
        logging={"payload_mode": "full", "file": data_dir / "logs" / "payload.log", "console": False},  # type: ignore[arg-type]
        development=DevelopmentSettings(enabled=True),
    )

    assert valid.logging.payload_mode == "full"
    for logging, message in (
        ({"payload_mode": "full", "file": data_dir / "payload.log", "console": True}, "console=false"),
        (
            {"payload_mode": "full", "file": data_dir / "payload.log", "console": False, "json_lines": True},
            "json_lines=false",
        ),
        ({"payload_mode": "full", "file": tmp_path / "outside.log", "console": False}, "below core.data_dir"),
    ):
        with pytest.raises(ValidationError, match=message):
            AppSettings(
                core={"data_dir": data_dir},  # type: ignore[arg-type]
                logging=logging,  # type: ignore[arg-type]
                development=DevelopmentSettings(enabled=True),
            )


def test_v5_rejects_legacy_runtime_configuration() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        AppSettings.model_validate({"config_version": 5, "runtimes": {"source": {"kind": "nonebot"}}})
    with pytest.raises(ValidationError, match="Extra inputs"):
        AppSettings.model_validate(
            {"config_version": 5, "runtime_event_routes": [{"sources": ["source"], "target": "target"}]}
        )


def test_nested_includes_merge_in_declared_order(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "first.json").write_text('{"core": {"queue_capacity": 5, "max_concurrent_events": 8}}', encoding="utf-8")
    (nested / "second.toml").write_text("[core]\nqueue_capacity = 6\n", encoding="utf-8")
    (tmp_path / "primary.toml").write_text(
        "config_version = 5\n"
        'include = ["nested/first.json", "nested/second.toml"]\n'
        "[core]\nhandler_timeout_seconds = 12\n",
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
config_version = 5
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
    (tmp_path / "a.toml").write_text('config_version = 5\ninclude = ["b.toml"]\n', encoding="utf-8")
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
    yaml_path.write_text("config_version: 5\ncore:\n  queue_capacity: 7\n", encoding="utf-8")
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
    yaml_path.write_text("config_version: 5\ncore:\n  queue_capacity: 7\n", encoding="utf-8")
    fake_yaml = SimpleNamespace(safe_load=lambda value: {"config_version": 5, "core": {"queue_capacity": 7}})
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_yaml)

    settings = load_settings(yaml_path, environ={})

    assert settings.core.queue_capacity == 7


def test_http_is_restricted_to_loopback(tmp_path: Path) -> None:
    config_path = tmp_path / "remote.toml"
    config_path.write_text('config_version = 5\n[http]\nenabled = true\nhost = "0.0.0.0"\n', encoding="utf-8")

    with pytest.raises(ConfigurationError, match="HTTP host must be a loopback address"):
        load_settings(config_path, environ={})

    settings = load_settings(
        config_path,
        environ={"LITEYUKI__HTTP__HOST": '"::1"'},
    )
    assert settings.http.host == "::1"
