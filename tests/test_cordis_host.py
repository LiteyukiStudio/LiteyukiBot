from __future__ import annotations

import sys
from types import ModuleType
from typing import Any, cast

import pytest
from liteyukibot_cordis import host_factory
from liteyukibot_cordis.host import PLUGIN_ENTRY_POINT_GROUP
from liteyukibot_cordis.scope import Scope

from liteyukibot.app import LiteyukiApp
from liteyukibot.config import AppSettings, ConfigWorkspace, CordisSettings, CoreSettings, PluginSettings, load_settings
from liteyukibot.cordis_host import CORDIS_HOST_ENTRY_POINT_GROUP, ActionServiceLike, discover_cordis_host
from liteyukibot.events import EventBus
from liteyukibot.logging import Logger
from liteyukibot.plugins import PluginContext, PluginDefinition, PluginHandle, PluginManifest


class _EntryPoint:
    def __init__(self, name: str, value: object) -> None:
        self.name = name
        self._value = value

    def load(self) -> object:
        return self._value


class _Host:
    def __init__(self, events: EventBus, calls: list[str], *, fail_start: bool = False) -> None:
        self._events = events
        self._calls = calls
        self._fail_start = fail_start

    async def start(self) -> None:
        self._calls.append("cordis.start")
        if self._fail_start:
            raise RuntimeError("Cordis host start failed")

    async def aclose(self) -> None:
        assert not self._events.closed
        self._calls.append("cordis.close")


def _settings(*enabled: str) -> CordisSettings:
    return CordisSettings(enabled=enabled, config={"example": {"nested": ["value"]}})


def test_cordis_settings_are_frozen_and_workspace_template_round_trips(tmp_path: Any) -> None:
    settings = _settings("example.plugin")
    assert settings.model_dump(mode="json") == {
        "enabled": ["example.plugin"],
        "config": {"example": {"nested": ["value"]}},
    }
    with pytest.raises(TypeError):
        settings.config["other"] = {}  # type: ignore[index]

    path = ConfigWorkspace(tmp_path).initialize(
        cordis_plugins=("example.plugin",),
        cordis_config={"example.plugin": {"mode": "full"}},
    )
    loaded = load_settings(path, environ={})

    assert loaded.cordis.enabled == ("example.plugin",)
    assert loaded.cordis.config == {"example.plugin": {"mode": "full"}}


def test_cordis_settings_reject_duplicate_or_untrimmed_plugin_ids() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        CordisSettings(enabled=("example", "example"))
    with pytest.raises(ValueError, match="surrounding whitespace"):
        CordisSettings(enabled=(" example",))
    with pytest.raises(ValueError, match="non-JSON"):
        CordisSettings(config={"invalid": object()})


def test_disabled_cordis_does_not_discover_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    def entry_points(**_kwargs: object) -> object:
        raise AssertionError("disabled Cordis must not inspect entry points")

    monkeypatch.setattr("liteyukibot.cordis_host.metadata.entry_points", entry_points)

    assert discover_cordis_host(
        CordisSettings(),
        events=EventBus(),
        actions=cast(ActionServiceLike, object()),
        logger=cast(Logger, object()),
    ) is None


@pytest.mark.parametrize(
    ("entry_points", "message"),
    (
        ((), "no liteyukibot.cordis_hosts implementation"),
        ((_EntryPoint("first", object()), _EntryPoint("second", object())), "exactly one host implementation"),
    ),
)
def test_enabled_cordis_requires_exactly_one_host(
    monkeypatch: pytest.MonkeyPatch, entry_points: tuple[_EntryPoint, ...], message: str
) -> None:
    monkeypatch.setattr(
        "liteyukibot.cordis_host.metadata.entry_points",
        lambda *, group: entry_points if group == CORDIS_HOST_ENTRY_POINT_GROUP else (),
    )

    with pytest.raises(RuntimeError, match=message):
        discover_cordis_host(
            _settings("example.plugin"),
            events=EventBus(),
            actions=cast(ActionServiceLike, object()),
            logger=cast(Logger, object()),
        )


@pytest.mark.asyncio
async def test_app_starts_and_closes_cordis_at_the_event_bus_boundary(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    plugin_module = ModuleType("test_cordis_native_plugin")

    async def setup(_context: PluginContext) -> PluginHandle:
        async def start() -> None:
            calls.append("native.start")

        async def stop() -> None:
            calls.append("native.stop")

        return PluginHandle(start=start, stop=stop)

    cast(Any, plugin_module).plugin = PluginDefinition(PluginManifest(id="native", name="Native", version="1"), setup)
    monkeypatch.setitem(sys.modules, plugin_module.__name__, plugin_module)

    captured: dict[str, object] = {}

    def factory(*, events: EventBus, actions: ActionServiceLike, settings: CordisSettings, logger: Logger) -> _Host:
        captured.update(events=events, actions=actions, settings=settings, logger=logger)
        return _Host(events, calls)

    entry_point = _EntryPoint("python", factory)
    monkeypatch.setattr(
        "liteyukibot.cordis_host.metadata.entry_points",
        lambda *, group: (entry_point,) if group == CORDIS_HOST_ENTRY_POINT_GROUP else (),
    )
    app = LiteyukiApp(
        AppSettings(
            core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
            plugins=PluginSettings(enabled=("native",), local_modules=(plugin_module.__name__,)),
            cordis=_settings("example.plugin"),
        )
    )

    await app.start()
    assert calls == ["native.start", "cordis.start"]
    assert captured["events"] is app.events
    assert captured["actions"] is app.actions
    assert captured["settings"] is app.settings.cordis
    await app.stop()

    assert calls == ["native.start", "cordis.start", "cordis.close", "native.stop"]


@pytest.mark.asyncio
async def test_app_closes_a_partially_started_cordis_host(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def factory(*, events: EventBus, **_kwargs: object) -> _Host:
        return _Host(events, calls, fail_start=True)

    entry_point = _EntryPoint("python", factory)
    monkeypatch.setattr(
        "liteyukibot.cordis_host.metadata.entry_points",
        lambda *, group: (entry_point,) if group == CORDIS_HOST_ENTRY_POINT_GROUP else (),
    )
    app = LiteyukiApp(
        AppSettings(
            core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
            cordis=_settings("example.plugin"),
        )
    )

    with pytest.raises(RuntimeError, match="Cordis host start failed"):
        await app.start()

    assert calls == ["cordis.start", "cordis.close"]


@pytest.mark.asyncio
async def test_app_starts_the_discovered_cordis_package_and_plugin(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    activated: list[dict[str, object]] = []

    async def plugin(scope: Scope) -> None:
        activated.append(dict(scope.config))

    host_entry = _EntryPoint("python", host_factory)
    plugin_entry = _EntryPoint("example.plugin", plugin)

    def entry_points(*, group: str) -> tuple[_EntryPoint, ...]:
        if group == CORDIS_HOST_ENTRY_POINT_GROUP:
            return (host_entry,)
        if group == PLUGIN_ENTRY_POINT_GROUP:
            return (plugin_entry,)
        return ()

    monkeypatch.setattr("liteyukibot.cordis_host.metadata.entry_points", entry_points)
    app = LiteyukiApp(
        AppSettings(
            core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
            cordis=CordisSettings(enabled=("example.plugin",), config={"example.plugin": {"mode": "full"}}),
        )
    )

    await app.start()
    await app.stop()

    assert activated == [{"mode": "full"}]
