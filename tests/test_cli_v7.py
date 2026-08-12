from __future__ import annotations

import signal
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest
from filelock import Timeout

import liteyukibot.cli as cli_module
from liteyukibot.config import AppSettings
from liteyukibot.init_wizard import InitWizardResult
from liteyukibot.plugin_store import PlatformTarget, RuntimeGeneration, RuntimeGenerationStore


class StubApp:
    calls: ClassVar[list[str]] = []

    def __init__(self, _settings: AppSettings) -> None:
        pass

    async def start(self) -> None:
        self.calls.append("start")

    async def stop(self) -> None:
        self.calls.append("stop")


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


@pytest.mark.asyncio
async def test_run_until_signal_uses_event_loop_signal_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = FakeSignalLoop(supports_async_handlers=True)
    StubApp.calls = []
    monkeypatch.setattr(cli_module, "LiteyukiApp", StubApp)
    monkeypatch.setattr("liteyukibot.cli.asyncio.get_running_loop", lambda: loop)

    await cli_module._run_until_signal(AppSettings())

    assert StubApp.calls == ["start", "stop"]
    assert loop.added == [signal.SIGINT, signal.SIGTERM]
    assert loop.removed == [signal.SIGINT, signal.SIGTERM]


@pytest.mark.asyncio
async def test_run_until_signal_uses_windows_signal_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = FakeSignalLoop(supports_async_handlers=False)
    previous = object()
    assignments: list[tuple[signal.Signals, Any]] = []
    StubApp.calls = []

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


def test_run_rejects_an_active_workspace_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from liteyukibot.config import ConfigWorkspace

    ConfigWorkspace(tmp_path).initialize()

    class LockedFileLock:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> None:
            raise Timeout("instance.lock")

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(cli_module, "FileLock", LockedFileLock)
    monkeypatch.setattr(cli_module, "_runtime_secrets", lambda *_args: (_ for _ in ()).throw(AssertionError()))

    assert cli_module.main(["--workspace", str(tmp_path), "run"]) == 2
    assert "another LiteyukiBot command is active" in capsys.readouterr().err


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


def test_plugin_disable_and_enable_cli_dispatch_to_the_runtime_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from liteyukibot.config import ConfigWorkspace

    ConfigWorkspace(tmp_path).initialize(runtimes={"legacy": {"kind": "v6"}})
    calls: list[tuple[str, str, str, str]] = []

    class InstallationService:
        def __init__(self, workspace: Path) -> None:
            assert workspace == tmp_path

        def disable(self, bundle_id: str, *, runtime_id: str, runtime_kind: str) -> SimpleNamespace:
            calls.append(("disable", bundle_id, runtime_id, runtime_kind))
            return SimpleNamespace(generation=SimpleNamespace(id="disabled-generation"))

        def enable(self, bundle_id: str, *, runtime_id: str, runtime_kind: str) -> SimpleNamespace:
            calls.append(("enable", bundle_id, runtime_id, runtime_kind))
            return SimpleNamespace(generation=SimpleNamespace(id="enabled-generation"))

    monkeypatch.setattr(cli_module, "PluginInstallationService", InstallationService)

    assert (
        cli_module.main(["--workspace", str(tmp_path), "plugin", "disable", "example.echo", "--runtime", "legacy"])
        == 0
    )
    assert capsys.readouterr().out.strip() == "disabled example.echo; activated disabled-generation"
    assert (
        cli_module.main(["--workspace", str(tmp_path), "plugin", "enable", "example.echo", "--runtime", "legacy"])
        == 0
    )
    assert capsys.readouterr().out.strip() == "enabled example.echo; activated enabled-generation"
    assert calls == [("disable", "example.echo", "legacy", "v6"), ("enable", "example.echo", "legacy", "v6")]
