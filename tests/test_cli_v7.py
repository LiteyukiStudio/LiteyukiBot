from __future__ import annotations

import asyncio
import json
import multiprocessing
import signal
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

import liteyukibot.cli as cli_module
from liteyukibot import LiteyukiApp
from liteyukibot.config import ConfigWorkspace, load_settings
from liteyukibot.instances import InstanceRegistry, InstanceRegistryError


def _register_instance_worker(registry_path: str, name: str, directory: str) -> str:
    return InstanceRegistry(registry_path).register(name, directory).name


def test_shutdown_signals_include_windows_ctrl_break_when_available() -> None:
    signals = cli_module._shutdown_signals()

    assert signal.SIGINT in signals
    assert signal.SIGTERM in signals
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        assert sigbreak in signals


def test_help_describes_source_and_registered_instance_selection() -> None:
    help_text = cli_module.build_parser().format_help()

    assert "--workspace PATH_OR_NAME" in help_text
    assert "--instance NAME" in help_text
    assert "instance add dev PATH" in help_text
    assert "check --instance dev --format json" in help_text
    assert "help" in help_text


def test_help_command_prints_root_help_without_preparing_a_workspace(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli_module.main(["help"]) == 0

    output = capsys.readouterr()
    assert "usage: liteyuki" in output.out
    assert "{help,run,check" in output.out
    assert output.err == ""


def test_help_command_walks_nested_parser_paths_and_aliases(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli_module.main(["help", "config", "show"]) == 0
    output = capsys.readouterr()
    assert "usage: liteyuki config show" in output.out
    assert "--format {json,toml}" in output.out

    assert cli_module.main(["help", "workspace", "list"]) == 0
    output = capsys.readouterr()
    assert "usage: liteyuki instance list" in output.out


@pytest.mark.parametrize("flag", ("-h", "--help"))
def test_help_prefix_form_targets_a_command_without_argparse_error(
    flag: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli_module.main([flag, "check"]) == 0

    output = capsys.readouterr()
    assert "usage: liteyuki check" in output.out
    assert output.err == ""


def test_help_command_reports_unknown_command_paths(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli_module.main(["help", "missing"]) == 2

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "unknown command path: missing\n"


def test_instance_registry_round_trip_keeps_directory_on_unregistration(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    instance_path = tmp_path / "instance"
    registry = InstanceRegistry(registry_path)

    record = registry.register("dev", instance_path)
    registry.set_default("DEV")

    loaded = InstanceRegistry(registry_path)
    assert loaded.resolve("dev") == record
    assert loaded.default() == record
    assert loaded.list() == (record,)

    removed = loaded.remove("dev")

    assert removed == record
    assert loaded.list() == ()
    assert loaded.default() is None
    assert not instance_path.exists()


def test_instance_registry_keeps_concurrent_registrations(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    context = multiprocessing.get_context("spawn")

    with ProcessPoolExecutor(max_workers=4, mp_context=context) as executor:
        futures = [
            executor.submit(
                _register_instance_worker,
                str(registry_path),
                f"worker-{index}",
                str(tmp_path / f"instance-{index}"),
            )
            for index in range(4)
        ]
        assert sorted(future.result(timeout=10) for future in futures) == [
            "worker-0",
            "worker-1",
            "worker-2",
            "worker-3",
        ]

    assert {record.name for record in InstanceRegistry(registry_path).list()} == {
        "worker-0",
        "worker-1",
        "worker-2",
        "worker-3",
    }


@pytest.mark.parametrize("name", ("", "bad/name", "bad name", "中文"))
def test_instance_registry_rejects_unportable_nicknames(tmp_path: Path, name: str) -> None:
    with pytest.raises(InstanceRegistryError, match="instance nickname"):
        InstanceRegistry(tmp_path / "registry.json").register(name, tmp_path / "instance")


def test_cli_nickname_selects_a_registered_instance_and_supports_leaf_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry_path = tmp_path / "registry.json"
    instance_path = tmp_path / "instance"
    monkeypatch.setenv("LITEYUKI_INSTANCE_REGISTRY", str(registry_path))

    assert cli_module.main(["instance", "add", "dev", str(instance_path)]) == 0
    assert cli_module.main(["init", "--instance", "dev", "--locale", "en-US"]) == 0
    assert cli_module.main(["check", "--workspace", "dev", "--format", "json"]) == 0

    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result == {"config_version": 7, "valid": True}


def test_cli_uses_selected_default_instance_when_cwd_has_no_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry_path = tmp_path / "registry.json"
    instance_path = tmp_path / "instance"
    current_directory = tmp_path / "cwd"
    current_directory.mkdir()
    monkeypatch.setenv("LITEYUKI_INSTANCE_REGISTRY", str(registry_path))
    monkeypatch.chdir(current_directory)

    assert cli_module.main(["instance", "add", "dev", str(instance_path)]) == 0
    assert cli_module.main(["instance", "use", "dev"]) == 0
    assert cli_module.main(["init"]) == 0
    assert cli_module.main(["check"]) == 0

    assert (instance_path / "liteyuki.toml").is_file()
    assert "configuration valid" in capsys.readouterr().out


def test_cli_instance_list_json_marks_the_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("LITEYUKI_INSTANCE_REGISTRY", str(registry_path))

    assert cli_module.main(["instance", "add", "dev", str(tmp_path / "instance")]) == 0
    assert cli_module.main(["instance", "use", "dev"]) == 0
    capsys.readouterr()
    assert cli_module.main(["workspace", "list", "--format", "json"]) == 0

    document = json.loads(capsys.readouterr().out)
    assert document["default"] == "dev"
    assert document["instances"][0]["default"] is True


def test_debug_parser_supports_bounded_ablation_sessions() -> None:
    args = cli_module.build_parser().parse_args(
        ["tests", "debug", "--workspace", "dev", "--duration", "0", "--ablate", "all"]
    )

    assert args.command == "tests"
    assert args.tests_command == "debug"
    assert args.duration == 0
    assert args.ablate == ["all"]


def test_cli_tests_debug_emits_jsonl_lifecycle_and_applies_onebot_ablation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ConfigWorkspace(tmp_path).initialize(
        onebot={
            "v11": {
                "accounts": {
                    "remote": {
                        "implementation": "snowluma",
                        "self_id": "42",
                        "ws_url": "ws://example.invalid/",
                    }
                }
            }
        }
    )

    assert (
        cli_module.main(
            [
                "tests",
                "debug",
                "--workspace",
                str(tmp_path),
                "--duration",
                "1.0",
                "--ablate",
                "onebot",
                "--log-tail",
                "0",
            ]
        )
        == 0
    )

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [record["kind"] for record in records] == ["started", "ready", "snapshot", "stopped"]
    assert records[0]["ablations"] == ["onebot"]
    assert records[1]["status"]["state"] == "ready"
    assert "onebot" not in records[1]["status"]
    assert any(record["kind"] == "snapshot" for record in records)
    assert records[-1]["status"]["state"] == "stopped"


@pytest.mark.asyncio
async def test_cli_tests_debug_bounds_startup_to_the_session_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = ConfigWorkspace(tmp_path).initialize()
    settings = load_settings(config, environ={})

    async def delayed_startup(_self: object) -> None:
        await asyncio.sleep(10)

    monkeypatch.setattr(LiteyukiApp, "_start_cordis", delayed_startup)

    result = await asyncio.wait_for(
        cli_module._debug_session(
            settings,
            workspace=tmp_path,
            duration=0.01,
            interval=0.01,
            output_format="jsonl",
            ablations=(),
            log_tail=0,
        ),
        timeout=1,
    )

    assert result == 2
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [record["kind"] for record in records] == ["started", "failed", "stopped"]
    assert records[1]["error"]["message"] == "debug startup exceeded session deadline"


def test_cli_tests_debug_returns_configured_log_tail(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ConfigWorkspace(tmp_path).initialize()

    assert (
        cli_module.main(
            [
                "tests",
                "debug",
                "--workspace",
                str(tmp_path),
                "--duration",
                "0",
                "--set",
                "logging.file=debug.log",
                "--set",
                "logging.console=false",
                "--log-tail",
                "5",
            ]
        )
        == 0
    )

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    stopped = records[-1]
    assert stopped["kind"] == "stopped"
    assert stopped["log_file"] == str((tmp_path / "debug.log").resolve())
    assert any("LiteyukiBot is ready" in line for line in stopped["logs"])


def test_cli_tests_debug_applies_plugin_ablation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ConfigWorkspace(tmp_path).initialize(cordis_plugins=("missing.plugin",))

    assert (
        cli_module.main(
            [
                "tests",
                "debug",
                "--workspace",
                str(tmp_path),
                "--duration",
                "0",
                "--ablate",
                "plugins",
                "--log-tail",
                "0",
            ]
        )
        == 0
    )

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    ready = next(record for record in records if record["kind"] == "ready")
    assert ready["ablations"] == ["plugins"]
    assert ready["status"]["state"] == "ready"


def test_cli_tests_debug_reports_startup_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ConfigWorkspace(tmp_path).initialize(cordis_plugins=("missing.plugin",))

    assert (
        cli_module.main(
            [
                "tests",
                "debug",
                "--workspace",
                str(tmp_path),
                "--duration",
                "0",
                "--log-tail",
                "0",
            ]
        )
        == 2
    )

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [record["kind"] for record in records] == ["started", "failed", "stopped"]
    assert records[1]["error"]["type"] == "RuntimeError"
    assert "missing.plugin" in records[1]["error"]["message"]
    assert records[-1]["status"]["state"] == "stopped"
