from __future__ import annotations

import signal
from collections.abc import Callable
from typing import Any, ClassVar

import pytest

import liteyukibot.cli as cli_module
from liteyukibot.config import AppSettings


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
