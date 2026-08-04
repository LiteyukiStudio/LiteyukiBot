from __future__ import annotations

import asyncio
import importlib.util
import json
import socket
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from urllib.request import urlopen

import pytest

from liteyukibot.app import AppState, LiteyukiApp
from liteyukibot.config import AppSettings, CoreSettings, HttpSettings, PluginSettings
from liteyukibot.control import ControlError, request_control
from liteyukibot.exceptions import PluginError
from liteyukibot.plugins import PluginDefinition, PluginHandle, PluginManifest
from liteyukibot.services import ServiceKey, ServiceRequirement


class FakeLogger:
    def bind(self, **fields: Any) -> FakeLogger:
        return self

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass


@pytest.mark.asyncio
async def test_app_lifecycle_and_local_control(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    await app.start()
    assert app.state.value == AppState.READY
    descriptor = settings.core.data_dir / "control.json"
    assert descriptor.is_file()
    status = await request_control(descriptor, "status")
    assert status["state"] == "ready"
    assert status["plugins"] == {}
    assert status["runtimes"] == {}

    await app.stop()
    assert app.state.value == AppState.STOPPED
    assert not descriptor.exists()
    with pytest.raises(ControlError, match="cannot read control descriptor"):
        await request_control(descriptor, "status")


@pytest.mark.asyncio
async def test_startup_failure_stops_plugins_already_set_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ServiceKey("test.startup")
    calls: list[str] = []

    async def first_setup(context: Any) -> PluginHandle:
        context.services.provide(service, "ready")
        calls.append("first.setup")

        async def stop() -> None:
            calls.append("first.stop")

        return PluginHandle(stop=stop)

    async def second_setup(context: Any) -> None:
        calls.append("second.setup")
        raise RuntimeError("setup failed")

    first = ModuleType("test_v7_first")
    cast(Any, first).plugin = PluginDefinition(
        PluginManifest(
            id="first",
            name="First",
            version="1",
            provides=(service,),
        ),
        first_setup,
    )
    second = ModuleType("test_v7_second")
    cast(Any, second).plugin = PluginDefinition(
        PluginManifest(
            id="second",
            name="Second",
            version="1",
            requires=(ServiceRequirement(service),),
        ),
        second_setup,
    )
    monkeypatch.setitem(sys.modules, first.__name__, first)
    monkeypatch.setitem(sys.modules, second.__name__, second)

    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        plugins=PluginSettings(
            enabled=("first", "second"),
            local_modules=(first.__name__, second.__name__),
        ),
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    with pytest.raises(PluginError, match="second setup failed"):
        await app.start()

    assert app.state is AppState.FAILED
    assert calls == ["first.setup", "second.setup", "first.stop"]
    assert app.services.get(service) is None


@pytest.mark.asyncio
@pytest.mark.skipif(importlib.util.find_spec("fastapi") is None, reason="HTTP extra is not installed")
async def test_optional_http_status_is_loopback_and_read_only(tmp_path: Path) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = cast(tuple[str, int], listener.getsockname())[1]
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        http=HttpSettings(enabled=True, port=port),
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    await app.start()
    try:
        response = await asyncio.to_thread(_get_json, f"http://127.0.0.1:{port}/status")
        assert response["state"] == "ready"
        assert response["plugins"] == {}
        assert response["runtimes"] == {}
    finally:
        await app.stop()


def _get_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=2) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise TypeError("expected a JSON object")
    return value
