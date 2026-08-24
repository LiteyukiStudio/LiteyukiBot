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

import liteyukibot.app as app_module
from liteyukibot import __version__
from liteyukibot.app import AppState, LiteyukiApp
from liteyukibot.config import (
    AppSettings,
    BrokerBridgeSettings,
    BrokerSettings,
    CoreSettings,
    HttpSettings,
    PluginSettings,
)
from liteyukibot.control import ControlError, ControlServer, request_control
from liteyukibot.events import (
    ActionEnvelope,
    ActionResult,
    ActorRef,
    CallApi,
    ConversationRef,
    EventEnvelope,
    Message,
    Segment,
    SendMessage,
)
from liteyukibot.exceptions import PluginError
from liteyukibot.functions import FunctionCall
from liteyukibot.plugins import PluginDefinition, PluginHandle, PluginManifest
from liteyukibot.resource_packs import write_resource_manifest
from liteyukibot.services import ServiceKey, ServiceRequirement
from liteyukibot.status import KERNEL_STATUS_SERVICE


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


class PermissionFixture:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.observed: list[tuple[EventEnvelope, str]] = []

    def allows(self, event: EventEnvelope, capability: str) -> bool:
        self.observed.append((event, capability))
        return self.allowed


class PermissionAuditFixture(PermissionFixture):
    def __init__(self, allowed: bool) -> None:
        super().__init__(allowed)
        self.decisions: list[tuple[EventEnvelope, str, str]] = []

    def decide(self, event: EventEnvelope, capability: str, *, component: str) -> bool:
        self.decisions.append((event, capability, component))
        return self.allowed


@pytest.mark.asyncio
@pytest.mark.skipif(
    importlib.util.find_spec("liteyukibot_functions") is None,
    reason="functions package is not installed",
)
async def test_app_shutdown_cancels_function_background_tasks(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    functions = workspace / "resources" / "legacy" / "functions"
    functions.mkdir(parents=True)
    (functions.parent / "metadata.yml").write_text(
        'id: legacy\nname: Legacy\nversion: "6"\n',
        encoding="utf-8",
    )
    (functions / "background.lyf").write_text("nohup sleep 60\n", encoding="utf-8")
    (workspace / "resources" / "index.json").write_text('["legacy"]', encoding="utf-8")
    write_resource_manifest(functions.parent)
    settings = AppSettings(core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"))
    app = LiteyukiApp(settings, logger=FakeLogger(), resource_workspace=str(workspace))  # type: ignore[arg-type]

    await app.start()
    assert app.functions is not None
    await app.functions.dispatch(FunctionCall("background", {}))
    await asyncio.sleep(0)
    assert app.functions.background_task_count == 1

    await app.stop()

    assert app.functions.background_task_count == 0


def test_kernel_status_service_is_available_before_plugin_resolution(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    provider = app.services.require(KERNEL_STATUS_SERVICE)
    snapshot = provider.snapshot()

    assert app.services.provider_for(KERNEL_STATUS_SERVICE) == "liteyukibot.kernel"
    assert snapshot.version == __version__
    assert snapshot.state == "created"
    assert snapshot.uptime_seconds == 0
    assert snapshot.plugins == {}
    assert snapshot.runtimes == {}
    assert snapshot.runtime_health == {}
    assert snapshot.events_outstanding == 0
    with pytest.raises(TypeError):
        cast(dict[str, str], snapshot.plugins)["unexpected"] = "ready"


@pytest.mark.asyncio
async def test_webui_presentation_is_resolved_from_kernel_resource_packs(tmp_path: Path) -> None:
    settings = AppSettings(core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"))
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    await app.start()
    try:
        presentation = await app._daemon_webui_presentation({"locale": "zh-CN"})
    finally:
        await app.stop()

    assert presentation["locale"] == "zh-CN"
    assert presentation["messages"]["webui.nav.overview"] == "概览"
    assert presentation["messages"]["webui.action.refresh"] == "刷新"


@pytest.mark.asyncio
async def test_kernel_status_uptime_freezes_after_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [10.0]
    monkeypatch.setattr(app_module, "monotonic", lambda: now[0])
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    await app.start()
    now[0] = 12.5
    assert app.status_snapshot().uptime_seconds == 2.5

    now[0] = 15.0
    await app.stop()
    now[0] = 99.0

    snapshot = app.status_snapshot()
    assert snapshot.state == "stopped"
    assert snapshot.uptime_seconds == 5.0


@pytest.mark.asyncio
async def test_kernel_status_uptime_freezes_after_startup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [20.0]
    monkeypatch.setattr(app_module, "monotonic", lambda: now[0])
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    async def fail_start() -> None:
        now[0] = 23.0
        raise RuntimeError("startup failed")

    monkeypatch.setattr(app.events, "start", fail_start)

    with pytest.raises(RuntimeError, match="startup failed"):
        await app.start()

    now[0] = 99.0
    snapshot = app.status_snapshot()
    assert snapshot.state == "failed"
    assert snapshot.uptime_seconds == 3.0


def test_plugin_topology_can_require_kernel_status(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    async def setup(_context: Any) -> None:
        return None

    definition = PluginDefinition(
        PluginManifest(
            id="status-consumer",
            name="Status consumer",
            version="1",
            requires=(ServiceRequirement(KERNEL_STATUS_SERVICE),),
        ),
        setup,
    )

    assert app.plugins.resolve_order({"status-consumer": definition}) == ("status-consumer",)


def test_topology_projects_configured_broker_bridges(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        broker=BrokerSettings(
            bridges={
                "kernel": BrokerBridgeSettings(
                    kind="kernel", token_secret="kernel-token", access="full", subscriptions=("*",)
                ),
                "onebot-primary": BrokerBridgeSettings(kind="onebot", token_secret="onebot-token"),
            }
        ),
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    topology = app.topology()

    assert topology["bridges"] == [{"id": "onebot-primary", "kind": "onebot", "state": "configured"}]
    assert topology["runtimes"] == []


@pytest.mark.asyncio
async def test_app_call_api_requires_exact_event_capability_before_action_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"))
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    source = EventEnvelope(
        id="event-1",
        runtime_id="adapter",
        adapter="onebot-v11",
        bot_id="bot-1",
        type="message.group.normal",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=ActorRef(id="user-1"),
    )
    action = ActionEnvelope(
        action_id="call-1",
        event_id=source.id,
        runtime_id=source.runtime_id,
        bot_id=source.bot_id,
        action=CallApi(api="get_status"),
    )
    executed: list[ActionEnvelope] = []

    async def execute_action(_event: EventEnvelope | None, envelope: ActionEnvelope) -> ActionResult:
        executed.append(envelope)
        return ActionResult(action_id=envelope.action_id, success=True)

    monkeypatch.setattr(app.actions, "_backend", execute_action)
    denied = await app.actions.execute(action, event=source)

    assert denied.success is False
    assert denied.error_message == "adapter API action permission is denied"
    assert executed == []

    permissions = PermissionFixture(allowed=True)
    app.services.provide(ServiceKey("liteyukibot.permissions", 1), permissions, provider="test")
    allowed = await app.actions.execute(action, event=source)

    assert allowed.success is True
    assert permissions.observed == [(source, "liteyukibot.adapter.call_api")]
    assert executed == [action]


@pytest.mark.asyncio
async def test_app_call_api_uses_permission_audit_extension_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"))
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    source = EventEnvelope(
        id="event-1",
        runtime_id="adapter",
        adapter="onebot-v11",
        bot_id="bot-1",
        type="message.group.normal",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=ActorRef(id="user-1"),
    )
    action = ActionEnvelope(
        action_id="call-1",
        event_id=source.id,
        runtime_id=source.runtime_id,
        bot_id=source.bot_id,
        action=CallApi(api="get_status"),
    )
    permissions = PermissionAuditFixture(allowed=False)
    app.services.provide(ServiceKey("liteyukibot.permissions", 1), permissions, provider="test")

    async def execute_unexpectedly(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("denied CallApi reached the action backend")

    monkeypatch.setattr(app.actions, "_backend", execute_unexpectedly)
    result = await app.actions.execute(action, event=source)

    assert result.success is False
    assert result.error_code == "ACTION_PERMISSION_DENIED"
    assert permissions.observed == []
    assert permissions.decisions == [(source, "liteyukibot.adapter.call_api", "adapter.call_api")]


@pytest.mark.asyncio
async def test_app_action_service_refuses_call_api_without_a_source_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"))
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    action = ActionEnvelope(
        action_id="call-1",
        runtime_id="adapter",
        bot_id="bot-1",
        action=CallApi(api="get_status"),
    )

    async def execute_unexpectedly(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("unauthorized CallApi reached the action backend")

    monkeypatch.setattr(app.actions, "_backend", execute_unexpectedly)

    result = await app.actions.execute(action)

    assert result.success is False
    assert result.error_code == "ACTION_PERMISSION_DENIED"
    assert result.error_message == "adapter API action requires a source event"


@pytest.mark.asyncio
async def test_app_action_without_active_broker_delivery_is_unavailable(tmp_path: Path) -> None:
    settings = AppSettings(core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"))
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    action = ActionEnvelope(
        action_id="send-1",
        runtime_id="adapter",
        bot_id="bot-1",
        action=SendMessage(
            message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
            reply_token="reply-token",
        ),
    )

    result = await app.actions.execute(action)

    assert result.success is False
    assert result.error_code == "RUNTIME_UNAVAILABLE"
    assert result.error_message == "no active Broker delivery can execute the action"


@pytest.mark.asyncio
async def test_app_action_uses_active_broker_delivery(tmp_path: Path) -> None:
    settings = AppSettings(core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"))
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    event = _message_event()
    action = ActionEnvelope(
        action_id="send-1",
        event_id=event.id,
        runtime_id=event.runtime_id,
        bot_id=event.bot_id,
        action=SendMessage(
            message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
            reply_token="reply-token",
        ),
    )
    observed: list[tuple[EventEnvelope, ActionEnvelope]] = []

    class ActiveBrokerPeer:
        async def execute_action(self, source: EventEnvelope, request: ActionEnvelope) -> ActionResult:
            observed.append((source, request))
            return ActionResult(action_id=request.action_id, success=True)

    app._kernel_broker_peer = cast(Any, ActiveBrokerPeer())

    result = await app.actions.execute(action, event=event)

    assert result.success is True
    assert observed == [(event, action)]


def _message_event() -> EventEnvelope:
    return EventEnvelope(
        id="event-1",
        runtime_id="adapter",
        adapter="onebot-v11",
        bot_id="bot-1",
        type="message.group.normal",
        conversation=ConversationRef(id="group-1", type="group"),
        message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
    )


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
    assert status["runtime_health"] == {}

    await app.stop()
    assert app.state.value == AppState.STOPPED
    assert not descriptor.exists()
    with pytest.raises(ControlError, match="cannot read control descriptor"):
        await request_control(descriptor, "status")


@pytest.mark.asyncio
async def test_app_rejects_restart_and_repeated_stop_is_safe(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    descriptor = settings.core.data_dir / "control.json"

    await app.start()
    with pytest.raises(RuntimeError, match="cannot start from state ready"):
        await app.start()
    assert descriptor.is_file()

    await app.stop()
    await app.stop()

    assert app.state is AppState.STOPPED
    assert not descriptor.exists()
    with pytest.raises(RuntimeError, match="cannot start from state stopped"):
        await app.start()


@pytest.mark.asyncio
async def test_startup_preserves_primary_error_when_cleanup_also_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    async def fail_start() -> None:
        raise RuntimeError("startup failed")

    async def fail_cleanup() -> None:
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(app.events, "start", fail_start)
    monkeypatch.setattr(app.events, "aclose", fail_cleanup)

    with pytest.raises(RuntimeError, match="startup failed") as raised:
        await app.start()

    assert app.state is AppState.FAILED
    assert any(
        "startup cleanup also failed: application cleanup failed" in note
        for note in getattr(raised.value, "__notes__", ())
    )


@pytest.mark.asyncio
async def test_control_descriptor_replacement_is_owner_safe(tmp_path: Path) -> None:
    descriptor = tmp_path / "data" / "control.json"

    first = ControlServer(
        descriptor,
        status_provider=lambda: {"instance": "first"},
    )
    second = ControlServer(
        descriptor,
        status_provider=lambda: {"instance": "second"},
    )

    await first.start()
    try:
        first_descriptor = json.loads(descriptor.read_text(encoding="utf-8"))
        await second.start()
        try:
            second_descriptor = json.loads(descriptor.read_text(encoding="utf-8"))
            assert second_descriptor["token"] != first_descriptor["token"]

            await first.stop()

            assert json.loads(descriptor.read_text(encoding="utf-8")) == second_descriptor
        finally:
            await second.stop()
    finally:
        await first.stop()

    assert not descriptor.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("descriptor", "message"),
    [
        ({"protocol": 1, "host": "192.0.2.1", "port": 1, "token": "secret"}, "loopback"),
        ({"protocol": 2, "host": "127.0.0.1", "port": 1, "token": "secret"}, "protocol"),
        ({"protocol": 1, "host": "127.0.0.1", "port": 0, "token": "secret"}, "port"),
    ],
)
async def test_control_rejects_untrusted_descriptor(
    tmp_path: Path, descriptor: dict[str, object], message: str
) -> None:
    path = tmp_path / "control.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")

    with pytest.raises(ControlError, match=message):
        await request_control(path, "status")


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
async def test_partial_plugin_startup_stops_handles_in_reverse_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ServiceKey("test.partial-start")
    calls: list[str] = []

    async def provider_setup(context: Any) -> PluginHandle:
        context.services.provide(service, "ready")
        calls.append("provider.setup")

        async def start() -> None:
            calls.append("provider.start")

        async def stop() -> None:
            calls.append("provider.stop")

        return PluginHandle(start=start, stop=stop)

    async def consumer_setup(context: Any) -> PluginHandle:
        assert context.services.require(service) == "ready"
        calls.append("consumer.setup")

        async def start() -> None:
            calls.append("consumer.start")
            raise RuntimeError("consumer start failed")

        async def stop() -> None:
            calls.append("consumer.stop")

        return PluginHandle(start=start, stop=stop)

    provider = ModuleType("test_v7_partial_provider")
    cast(Any, provider).plugin = PluginDefinition(
        PluginManifest(
            id="provider",
            name="Provider",
            version="1",
            provides=(service,),
        ),
        provider_setup,
    )
    consumer = ModuleType("test_v7_partial_consumer")
    cast(Any, consumer).plugin = PluginDefinition(
        PluginManifest(
            id="consumer",
            name="Consumer",
            version="1",
            requires=(ServiceRequirement(service),),
        ),
        consumer_setup,
    )
    monkeypatch.setitem(sys.modules, provider.__name__, provider)
    monkeypatch.setitem(sys.modules, consumer.__name__, consumer)

    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        plugins=PluginSettings(
            enabled=("provider", "consumer"),
            local_modules=(provider.__name__, consumer.__name__),
        ),
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="consumer start failed"):
        await app.start()

    assert app.state is AppState.FAILED
    assert calls == [
        "provider.setup",
        "consumer.setup",
        "provider.start",
        "consumer.start",
        "consumer.stop",
        "provider.stop",
    ]
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
