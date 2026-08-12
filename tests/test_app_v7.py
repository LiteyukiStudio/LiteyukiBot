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
    AgentSettings,
    AppSettings,
    CoreSettings,
    HttpSettings,
    PluginSettings,
    RuntimeEventRoute,
    RuntimeSettings,
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
from liteyukibot.runtime.protocol import EventAccepted, EventTrace
from liteyukibot.runtime.supervisor import ActionProvenance
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


@pytest.mark.asyncio
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


def test_topology_reports_redacted_runtime_edges_and_health(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        runtimes={
            "source": RuntimeSettings(kind="noop"),
            "target": RuntimeSettings(kind="noop"),
        },
        runtime_event_routes=(
            RuntimeEventRoute(sources=("source",), target="target", messages_only=True),
        ),
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    topology = app.topology()

    assert topology["schema_version"] == 1
    assert topology["kernel"] == {"version": __version__, "state": "created"}
    assert topology["plugins"] == []
    assert topology["runtimes"] == [
        {
            "id": "source",
            "kind": "noop",
            "enabled": True,
            "agent_harness": None,
            "health": {
                "kind": "noop",
                "state": "stopped",
                "connected": False,
                "protocol": None,
                "capabilities": (),
                "launch_count": 0,
                "heartbeat_age_seconds": None,
                "failures_in_window": 0,
                "pending_actions": 0,
                "pending_events": 0,
                "inbound_actions": 0,
                "inbound_events": 0,
                "inbound_agent_tools": 0,
                "active_deliveries": 0,
            },
        },
        {
            "id": "target",
            "kind": "noop",
            "enabled": True,
            "agent_harness": None,
            "health": {
                "kind": "noop",
                "state": "stopped",
                "connected": False,
                "protocol": None,
                "capabilities": (),
                "launch_count": 0,
                "heartbeat_age_seconds": None,
                "failures_in_window": 0,
                "pending_actions": 0,
                "pending_events": 0,
                "inbound_actions": 0,
                "inbound_events": 0,
                "inbound_agent_tools": 0,
                "active_deliveries": 0,
            },
        },
    ]
    assert topology["event_routes"] == [
        {"sources": ["source"], "target": "target", "messages_only": True}
    ]


@pytest.mark.asyncio
async def test_app_routes_child_action_to_distinct_adapter_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    action = ActionEnvelope(
        action_id="reply-1",
        event_id="event-1",
        runtime_id="adapter",
        bot_id="bot-1",
        action=SendMessage(
            message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
            reply_token="reply-token",
        ),
    )
    observed: list[ActionEnvelope] = []

    async def execute(envelope: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        observed.append(envelope)
        return ActionResult(
            action_id=envelope.action_id,
            success=True,
            data={"message_id": "sent-1"},
        )

    monkeypatch.setattr(app.actions, "execute", execute)
    result = await app._execute_runtime_action(
        "compat", action.model_dump(mode="json"), None
    )

    assert result.ok is True
    assert result.data == {
        "schema_version": 1,
        "action_id": "reply-1",
        "success": True,
        "data": {"message_id": "sent-1"},
        "error_code": None,
        "error_message": None,
    }
    assert observed == [action]


@pytest.mark.asyncio
async def test_app_rejects_invalid_and_self_targeted_child_actions(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    invalid = await app._execute_runtime_action("compat", {"invalid": True}, None)
    self_target = await app._execute_runtime_action(
        "compat",
        ActionEnvelope(
            action_id="reply-1",
            runtime_id="compat",
            bot_id="bot-1",
            action=SendMessage(
                message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
                reply_token="reply-token",
            ),
        ).model_dump(mode="json"),
        None,
    )

    assert invalid.ok is False
    assert invalid.error == "invalid ActionEnvelope"
    assert self_target.ok is False
    assert self_target.error == "child-originated action cannot target its source runtime"


@pytest.mark.asyncio
async def test_app_rejects_child_action_that_does_not_match_v4_source_event(tmp_path: Path) -> None:
    settings = AppSettings(core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"))
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    source = EventEnvelope(
        id="event-1",
        runtime_id="adapter",
        adapter="onebot-v11",
        bot_id="bot-1",
        type="message.group.normal",
        conversation=ConversationRef(id="group-1", type="group"),
    )
    action = ActionEnvelope(
        event_id="event-1",
        runtime_id="adapter",
        bot_id="other-bot",
        action=SendMessage(
            message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
            reply_token="reply-token",
        ),
    )
    provenance = ActionProvenance(
        delivery_correlation_id="delivery-1",
        trace=EventTrace(
            trace_id="event-1",
            source_runtime_id="adapter",
            source_event_id="event-1",
        ),
        event_payload=source.model_dump(mode="json"),
    )

    result = await app._execute_runtime_action("agent", action.model_dump(mode="json"), provenance)

    assert result.ok is False
    assert result.error == "child action does not match its source event provenance"


@pytest.mark.asyncio
async def test_app_call_api_requires_exact_event_capability_before_runtime_execution(
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
    provenance = ActionProvenance(
        delivery_correlation_id="delivery-1",
        trace=EventTrace(
            trace_id=source.id,
            source_runtime_id=source.runtime_id,
            source_event_id=source.id,
        ),
        event_payload=source.model_dump(mode="json"),
    )
    executed: list[ActionEnvelope] = []

    async def execute_action(
        _runtime_id: str,
        _correlation_id: str,
        payload: dict[str, Any],
        timeout_seconds: float = 30.0,
    ) -> object:
        assert timeout_seconds == 30.0
        envelope = ActionEnvelope.model_validate(payload)
        executed.append(envelope)
        return type("Response", (), {"ok": True, "data": None, "error": None})()

    monkeypatch.setattr(app.runtimes, "execute_action", execute_action)
    denied = await app._execute_runtime_action("agent", action.model_dump(mode="json"), provenance)

    assert denied.ok is False
    assert denied.error == "adapter API action permission is denied"
    assert executed == []

    permissions = PermissionFixture(allowed=True)
    app.services.provide(ServiceKey("liteyukibot.permissions", 1), permissions, provider="test")
    allowed = await app._execute_runtime_action("agent", action.model_dump(mode="json"), provenance)

    assert allowed.ok is True
    assert permissions.observed == [(source, "liteyukibot.adapter.call_api")]
    assert executed == [action]


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
        raise AssertionError("unauthorized CallApi reached the runtime supervisor")

    monkeypatch.setattr(app.runtimes, "execute_action", execute_unexpectedly)

    result = await app.actions.execute(action)

    assert result.success is False
    assert result.error_code == "ACTION_PERMISSION_DENIED"
    assert result.error_message == "adapter API action requires a source event"


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
async def test_app_event_bus_fans_out_messages_to_v6_runtimes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        runtimes={
            "legacy-a": RuntimeSettings(kind="v6"),
            "legacy-b": RuntimeSettings(kind="v6"),
            "nonebot": RuntimeSettings(kind="nonebot"),
        },
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    started: set[str] = set()
    both_started = asyncio.Event()

    async def dispatch(
        runtime_id: str,
        correlation_id: str,
        payload: dict[str, Any],
        timeout_seconds: float = 30.0,
    ) -> EventAccepted:
        assert correlation_id == "event-1"
        event = EventEnvelope.model_validate(payload)
        assert event.id == "event-1"
        assert event.message is not None and event.message.plain_text == "hello"
        assert timeout_seconds == 30.0
        started.add(runtime_id)
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=1)
        return EventAccepted(correlation_id=correlation_id, status="accepted")

    monkeypatch.setattr(app.runtimes, "dispatch_event", dispatch)
    try:
        result = await app.events.publish(_message_event().model_copy(update={"runtime_id": "nonebot"}))
    finally:
        await app.events.aclose()

    assert started == {"legacy-a", "legacy-b"}
    assert result.handlers_called == 1
    assert result.failures == ()


@pytest.mark.asyncio
async def test_app_v6_bridge_filters_non_messages_and_isolates_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        runtimes={
            "legacy-a": RuntimeSettings(kind="v6"),
            "legacy-b": RuntimeSettings(kind="v6"),
            "nonebot": RuntimeSettings(kind="nonebot"),
        },
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    delivered: list[str] = []

    async def dispatch(
        runtime_id: str,
        correlation_id: str,
        _payload: dict[str, Any],
        timeout_seconds: float = 30.0,
    ) -> EventAccepted:
        assert timeout_seconds == 30.0
        delivered.append(runtime_id)
        if runtime_id == "legacy-a":
            return EventAccepted(
                correlation_id=correlation_id,
                status="invalid",
                detail="fixture rejection",
            )
        return EventAccepted(correlation_id=correlation_id, status="accepted")

    monkeypatch.setattr(app.runtimes, "dispatch_event", dispatch)
    no_message_payload = _message_event().model_dump(mode="json")
    no_message_payload["runtime_id"] = "nonebot"
    no_message_payload["message"] = None
    try:
        ignored = await app.events.publish(EventEnvelope.model_validate(no_message_payload))
        rejected = await app.events.publish(_message_event().model_copy(update={"runtime_id": "nonebot"}))
    finally:
        await app.events.aclose()

    assert ignored.failures == ()
    assert delivered == ["legacy-a", "legacy-b"]
    assert len(rejected.failures) == 1
    assert rejected.failures[0].handler == "runtime.routes"
    assert "fixture rejection" in rejected.failures[0].message


@pytest.mark.asyncio
async def test_app_without_v6_runtime_does_not_register_bridge(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        runtimes={
            "nonebot": RuntimeSettings(kind="nonebot"),
            "disabled-legacy": RuntimeSettings(kind="v6", enabled=False),
        },
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    try:
        result = await app.events.publish(_message_event())
    finally:
        await app.events.aclose()

    assert result.handlers_called == 0


@pytest.mark.asyncio
async def test_app_routes_events_to_configured_external_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        runtimes={
            "nonebot": RuntimeSettings(kind="nonebot"),
            "astrbot": RuntimeSettings(kind="custom", command=("astrbot-runtime",)),
        },
        runtime_event_routes=(
            RuntimeEventRoute(sources=("nonebot",), target="astrbot", messages_only=True),
        ),
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]
    delivered: list[tuple[str, str]] = []

    async def dispatch(
        runtime_id: str,
        correlation_id: str,
        payload: dict[str, Any],
        timeout_seconds: float = 30.0,
    ) -> EventAccepted:
        assert timeout_seconds == 30.0
        delivered.append((runtime_id, EventEnvelope.model_validate(payload).id))
        return EventAccepted(correlation_id=correlation_id, status="accepted")

    monkeypatch.setattr(app.runtimes, "dispatch_event", dispatch)
    try:
        result = await app.events.publish(_message_event().model_copy(update={"runtime_id": "nonebot"}))
    finally:
        await app.events.aclose()

    assert delivered == [("astrbot", "event-1")]
    assert result.failures == ()


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
async def test_app_creates_a_private_runtime_state_directory(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        runtimes={"runtime": RuntimeSettings(kind="noop")},
    )
    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    await app.start()
    try:
        assert (tmp_path / "data" / "runtimes" / "runtime").is_dir()
        assert app.runtimes.records["runtime"].spec.env["LITEYUKI_RUNTIME_STATE_DIR"] == str(
            (tmp_path / "data" / "runtimes" / "runtime").resolve()
        )
    finally:
        await app.stop()


def test_agent_harness_generates_a_messages_only_route(tmp_path: Path) -> None:
    settings = AppSettings(
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        agent=AgentSettings(enabled=True, agent_harness="native"),
        runtimes={
            "source": RuntimeSettings(kind="noop"),
            "native": RuntimeSettings(kind="agent"),
        },
    )

    app = LiteyukiApp(settings, logger=FakeLogger())  # type: ignore[arg-type]

    assert app._runtime_event_routes == (
        RuntimeEventRoute(sources=("source",), target="native", messages_only=True),
    )
    assert app.runtimes.records["native"].spec.agent_harness == "native"


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

    async def restart(_runtime_id: str) -> None:
        return None

    first = ControlServer(
        descriptor,
        status_provider=lambda: {"instance": "first"},
        runtime_restarter=restart,
    )
    second = ControlServer(
        descriptor,
        status_provider=lambda: {"instance": "second"},
        runtime_restarter=restart,
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
