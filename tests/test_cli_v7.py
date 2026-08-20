from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import webbrowser
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest
from filelock import Timeout

import liteyukibot.cli as cli_module
from liteyukibot.broker.service import BridgeCatalog
from liteyukibot.config import AppSettings, ConfigWorkspace, redact_config
from liteyukibot.config.vault import SecretVault
from liteyukibot.init_wizard import InitWizardResult
from liteyukibot.plugin_store import PlatformTarget, RuntimeGeneration, RuntimeGenerationStore


class StubApp:
    calls: ClassVar[list[str]] = []
    logs: ClassVar[list[tuple[str, float]]] = []

    def __init__(self, _settings: AppSettings) -> None:
        self.logger = SimpleNamespace(info=lambda message, value: self.logs.append((message, value)))

    async def start(self) -> None:
        self.calls.append("start")

    async def stop(self) -> None:
        self.calls.append("stop")

    def set_stop_callback(self, _callback: Callable[[], None]) -> None:
        pass


class FakeSignalLoop:
    def __init__(self, *, supports_async_handlers: bool) -> None:
        self.supports_async_handlers = supports_async_handlers
        self.added: list[signal.Signals] = []
        self.removed: list[signal.Signals] = []

    def add_signal_handler(self, signum: signal.Signals, callback: Callable[[], None]) -> None:
        if not self.supports_async_handlers:
            raise NotImplementedError
        self.added.append(signum)
        callback()

    def remove_signal_handler(self, signum: signal.Signals) -> bool:
        self.removed.append(signum)
        return True

    def call_soon_threadsafe(self, callback: Callable[[], None]) -> None:
        callback()


def test_runtime_secrets_loads_configured_kernel_bridge_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = ConfigWorkspace(tmp_path)
    settings = AppSettings.model_validate(
        {
            "config_version": 5,
            "broker": {
                "bridges": {
                    "kernel": {
                        "kind": "kernel",
                        "token_secret": "broker.kernel.token",
                        "access": "full",
                        "subscriptions": ["message.created"],
                    }
                }
            },
        }
    )
    SecretVault(workspace.management_directory).initialize("password", {"broker.kernel.token": "secret-token"})
    monkeypatch.setattr(cli_module, "_vault_password", lambda _workspace: "password")

    assert cli_module._runtime_secrets(settings, workspace) == {"broker.kernel.token": "secret-token"}


@pytest.mark.asyncio
async def test_bridge_command_rejects_reserved_kernel_before_reading_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings.model_validate(
        {
            "config_version": 5,
            "broker": {
                "bridges": {
                    "kernel": {
                        "kind": "kernel",
                        "token_secret": "broker.kernel.token",
                        "access": "full",
                        "subscriptions": ["message.created"],
                    }
                }
            },
        }
    )
    monkeypatch.setattr(
        SecretVault,
        "read",
        lambda *_args: pytest.fail("kernel bridge must not read the vault through bridge run"),
    )

    with pytest.raises(RuntimeError, match="reserved kernel bridge"):
        await cli_module._bridge_command(settings, ConfigWorkspace(tmp_path), "kernel")


@pytest.mark.asyncio
async def test_bridge_command_resolves_secret_refs_in_launcher_only_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = ConfigWorkspace(tmp_path)
    settings = AppSettings.model_validate(
        {
            "config_version": 5,
            "broker": {
                "bridges": {
                    "adapter": {
                        "kind": "adapter",
                        "token_secret": "bridge.token",
                        "action_resources": [
                            {"kind": "message.send", "resource": "bot:adapter:bot"},
                        ],
                        "options": {
                            "adapters": {
                                "main": {
                                    "kind": "onebot-v11",
                                    "bot_id": "bot",
                                    "config": {"access_token": {"secret_ref": "onebot-token"}},
                                }
                            }
                        },
                    }
                }
            },
        }
    )
    SecretVault(workspace.management_directory).initialize(
        "password", {"bridge.token": "bridge-token", "onebot-token": "adapter-secret"}
    )
    monkeypatch.setattr(cli_module, "_vault_password", lambda _workspace: "password")
    captured: dict[str, Any] = {}

    async def launch(_self: Any, resolved: AppSettings, resolved_id: str, token: str) -> None:
        captured.update(settings=resolved, bridge_id=resolved_id, token=token)

    monkeypatch.setattr(BridgeCatalog, "launch", launch)

    await cli_module._bridge_command(settings, workspace, "adapter")

    resolved = cast(AppSettings, captured["settings"])
    assert captured["bridge_id"] == "adapter"
    assert captured["token"] == "bridge-token"
    resolved_options = cast(Any, resolved.broker.bridges["adapter"].options)
    original_options = cast(Any, settings.broker.bridges["adapter"].options)
    assert resolved_options["adapters"]["main"]["config"]["access_token"] == "adapter-secret"
    assert original_options["adapters"]["main"]["config"]["access_token"] == {"secret_ref": "onebot-token"}
    assert "adapter-secret" not in str(redact_config(settings.model_dump(mode="json")))


@pytest.mark.asyncio
async def test_web_command_uses_daemon_control_and_opens_handoff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    requests: list[tuple[Path, str]] = []

    async def request(descriptor: Path, command: str) -> dict[str, str]:
        requests.append((descriptor, command))
        return {"url": "http://127.0.0.1:8123/#ticket=x"}

    monkeypatch.setattr(
        cli_module,
        "request_control",
        request,
    )
    opened: list[str] = []

    def open_url(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr(webbrowser, "open", open_url)

    await cli_module._web_command(
        ConfigWorkspace(tmp_path),
        argparse.Namespace(instance="default", web_command="open"),
    )

    assert requests == [(tmp_path / ".liteyuki" / "instances" / "default" / "daemon.json", "webui.open")]
    assert opened == ["http://127.0.0.1:8123/#ticket=x"]
    assert capsys.readouterr().out.strip() == "http://127.0.0.1:8123/#ticket=x"


@pytest.mark.asyncio
async def test_web_status_uses_daemon_control(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    async def request(_descriptor: Path, command: str) -> dict[str, str]:
        return {"mode": "always", "command": command}

    monkeypatch.setattr(cli_module, "request_control", request)

    await cli_module._web_command(
        ConfigWorkspace(tmp_path),
        argparse.Namespace(instance="default", web_command="status"),
    )

    assert '"command": "webui.status"' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_until_signal_uses_event_loop_signal_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = FakeSignalLoop(supports_async_handlers=True)
    StubApp.calls = []
    StubApp.logs = []
    monkeypatch.setattr(cli_module, "LiteyukiApp", StubApp)
    monkeypatch.setattr("liteyukibot.cli.asyncio.get_running_loop", lambda: loop)

    await cli_module._run_until_signal(AppSettings())

    assert StubApp.calls == ["start", "stop"]
    assert loop.added == [signal.SIGINT, signal.SIGTERM]
    assert loop.removed == [signal.SIGINT, signal.SIGTERM]
    assert StubApp.logs[0][0] == "LiteyukiBot startup completed in {:.2f} ms"


@pytest.mark.asyncio
async def test_run_until_signal_uses_windows_signal_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = FakeSignalLoop(supports_async_handlers=False)
    previous = object()
    assignments: list[tuple[signal.Signals, Any]] = []
    StubApp.calls = []
    StubApp.logs = []

    def get_signal(_signum: signal.Signals) -> object:
        return previous

    def set_signal(signum: signal.Signals, handler: Any) -> object:
        assignments.append((signum, handler))
        if callable(handler):
            handler(signum, None)
        return previous

    monkeypatch.setattr(cli_module, "LiteyukiApp", StubApp)
    monkeypatch.setattr("liteyukibot.cli.asyncio.get_running_loop", lambda: loop)
    monkeypatch.setattr("liteyukibot.cli.signal.getsignal", get_signal)
    monkeypatch.setattr("liteyukibot.cli.signal.signal", set_signal)

    await cli_module._run_until_signal(AppSettings())

    assert StubApp.calls == ["start", "stop"]
    assert loop.added == []
    assert loop.removed == []
    assert [signum for signum, _handler in assignments] == [
        signal.SIGINT,
        signal.SIGTERM,
        signal.SIGINT,
        signal.SIGTERM,
    ]
    assert assignments[-2:] == [(signal.SIGINT, previous), (signal.SIGTERM, previous)]


def test_worker_rejects_an_active_data_directory_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from liteyukibot.config import ConfigWorkspace

    workspace = ConfigWorkspace(tmp_path)
    workspace.initialize()
    expected_data_directory = tmp_path / "data"
    lock_paths: list[Path] = []

    class LockedFileLock:
        def __init__(self, path: Path, **_kwargs: object) -> None:
            lock_paths.append(path)

        def __enter__(self) -> None:
            raise Timeout("instance.lock")

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(cli_module, "FileLock", LockedFileLock)
    assert cli_module.main(["--workspace", str(tmp_path), "run", "--daemon-worker"]) == 2
    assert lock_paths == [expected_data_directory / "instance.lock"]
    message = f"another LiteyukiBot instance is active for data directory {expected_data_directory}"
    assert message in capsys.readouterr().err


def test_worker_rejects_a_shared_data_directory_owned_by_another_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from liteyukibot.config import ConfigWorkspace

    first_workspace = ConfigWorkspace(tmp_path / "first")
    second_workspace = ConfigWorkspace(tmp_path / "second")
    first_workspace.initialize()
    second_workspace.initialize()
    data_directory = tmp_path / "shared-data"
    data_directory.mkdir()
    helper = """
from filelock import FileLock
from pathlib import Path
import sys
import time

with FileLock(Path(sys.argv[1]) / 'instance.lock', timeout=0):
    print('locked', flush=True)
    time.sleep(60)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", helper, str(data_directory)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "locked"
        assert (
            cli_module.main(
                [
                    "--workspace",
                    str(second_workspace.directory),
                        "--set",
                        f"core.data_dir={data_directory}",
                        "run",
                        "--daemon-worker",
                ]
            )
            == 2
        )
        message = f"another LiteyukiBot instance is active for data directory {data_directory}"
        assert message in capsys.readouterr().err
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_data_directory_locks_are_independent(tmp_path: Path) -> None:
    first_data_directory = tmp_path / "first-data"
    second_data_directory = tmp_path / "second-data"
    first_data_directory.mkdir()
    helper = """
from filelock import FileLock
from pathlib import Path
import sys
import time

with FileLock(Path(sys.argv[1]) / 'instance.lock', timeout=0):
    print('locked', flush=True)
    time.sleep(60)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", helper, str(first_data_directory)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "locked"
        with cli_module._exclusive_data_directory(second_data_directory):
            assert (second_data_directory / "instance.lock").is_file()
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_init_minimal_wizard_writes_locale_and_resource_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "wizard"
    monkeypatch.setattr(
        cli_module,
        "run_init_wizard",
        lambda *_args: InitWizardResult(str(workspace), "zh-CN", "minimal", None),
    )

    assert cli_module.main(["init"]) == 0
    assert 'locale = "zh-CN"' in (workspace / "liteyuki.toml").read_text(encoding="utf-8")
    assert (workspace / "resources" / "index.json").read_text(encoding="utf-8") == "[]\n"


def test_resource_manifest_and_verify_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "metadata.yml").write_text("id: test\nname: Test\nversion: 1\n", encoding="utf-8")

    assert cli_module.main(["resource", "manifest", str(pack)]) == 0
    assert capsys.readouterr().out.strip().endswith("manifest-v1.json")
    assert cli_module.main(["resource", "verify", str(pack)]) == 0
    assert capsys.readouterr().out.strip() == "resource manifest valid"


def test_inspect_topology_emits_the_resolved_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from liteyukibot.config import ConfigWorkspace

    ConfigWorkspace(tmp_path).initialize()

    class TopologyApp:
        def __init__(self, _settings: AppSettings) -> None:
            pass

        def topology(self, *, discover_plugins: bool) -> dict[str, object]:
            assert discover_plugins is True
            return {"schema_version": 1, "runtimes": []}

    monkeypatch.setattr(cli_module, "LiteyukiApp", TopologyApp)

    assert cli_module.main(["--workspace", str(tmp_path), "inspect", "topology"]) == 0
    assert capsys.readouterr().out.strip() == '{"schema_version": 1, "runtimes": []}'


def test_plugin_list_runtime_shows_managed_generation_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from liteyukibot.config import ConfigWorkspace

    ConfigWorkspace(tmp_path).initialize(runtimes={"legacy": {"kind": "v6"}})
    generation = RuntimeGeneration(
        "generation-one",
        "legacy",
        "v6",
        "2026-08-11T00:00:00+00:00",
        PlatformTarget("windows", "amd64", "3.14"),
        ("example.echo",),
        ("a" * 64,),
        {"modules": [], "directories": []},
    )
    store = RuntimeGenerationStore(tmp_path)
    store.write(generation)
    store.activate("legacy", generation.id)

    assert cli_module.main(["--workspace", str(tmp_path), "plugin", "list", "--runtime", "legacy"]) == 0

    assert capsys.readouterr().out.strip() == "active\tgeneration-one\t-\texample.echo\t-"


def test_plugin_runtime_operations_reject_unconfigured_legacy_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from liteyukibot.config import ConfigWorkspace

    ConfigWorkspace(tmp_path).initialize()

    assert cli_module.main(
        ["--workspace", str(tmp_path), "plugin", "disable", "example.echo", "--runtime", "legacy"]
    ) == 2
    assert "not configured" in capsys.readouterr().err
