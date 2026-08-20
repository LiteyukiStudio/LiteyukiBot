from __future__ import annotations

import importlib.metadata
from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any, cast

import pytest
from liteyukibot_runtime_mofox.host import (
    MoFoxBridgeHost,
    MoFoxHeadlessEngine,
    _enforce_headless_config,
    _install_upstream_namespace,
    _validate_bridge_settings,
    _workspace_path,
)
from liteyukibot_runtime_mofox.translate import to_mofox_envelope, to_mofox_event_input

from liteyukibot.broker import ActionResult, BrokerBridgeRunner, BrokerDelivery, BrokerEvent, EventMessage
from liteyukibot.config import AppSettings
from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope, Message, Segment


def _has_upstream_runtime() -> bool:
    try:
        importlib.metadata.distribution("neo-mofox")
    except PackageNotFoundError:
        return False
    return True


def _event() -> EventEnvelope:
    return EventEnvelope(
        id="event-1",
        runtime_id="nonebot",
        adapter="onebot",
        bot_id="bot-1",
        type="message",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=ActorRef(id="user-1", display_name="User"),
        message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
        reply_token="reply-1",
    )


def _delivery(runner: Any, event: EventEnvelope) -> BrokerDelivery:
    broker_event = BrokerEvent(
        kernel_event_id="kernel-event-1",
        source_bridge_id=event.runtime_id,
        source_event_id=event.id,
        topic="onebot.v11.message.group",
        ordering_key="bot-1:group:group-1",
        payload=event.model_dump(mode="json"),
    )
    return BrokerDelivery(
        cast(BrokerBridgeRunner, runner),
        EventMessage(
            delivery_id="delivery-1",
            lease_id="lease-1",
            lease_ttl_ms=5_000,
            event=broker_event,
        ),
    )


def test_mofox_translation_preserves_source_identity_and_wire_route() -> None:
    event = _event()
    translated = to_mofox_event_input(event)
    envelope = to_mofox_envelope(translated)

    assert translated.runtime_id == "nonebot"
    assert envelope["message_info"]["group_info"]["group_id"] == "group-1"
    assert envelope["message_segment"] == [{"type": "text", "data": "hello"}]
    assert envelope["raw_message"]["liteyuki_runtime"] == "nonebot"


def test_mofox_translation_preserves_non_text_segments_and_raw_source() -> None:
    event = _event().model_copy(
        update={
            "message": Message(
                segments=(
                    Segment(type="mention", data={"user_id": "other"}),
                    Segment(type="media", data={"media_type": "image", "url": "https://example.test/a.png"}),
                )
            ),
            "raw": {"source": "adapter"},
        }
    )

    envelope = to_mofox_envelope(to_mofox_event_input(event))

    assert envelope["message_segment"] == [
        {"type": "mention", "data": {"user_id": "other"}},
        {"type": "media", "data": {"media_type": "image", "url": "https://example.test/a.png"}},
    ]
    assert envelope["raw_message"]["source"] == {"source": "adapter"}


def test_mofox_translation_rejects_non_message_events() -> None:
    with pytest.raises(ValueError, match="message events"):
        to_mofox_event_input(_event().model_copy(update={"message": None}))


def test_mofox_headless_config_disables_listening_and_dynamic_install(tmp_path: Path) -> None:
    config = tmp_path / "config" / "core.toml"
    config.parent.mkdir()
    config.write_text("[http_router]\nenable_http_router = true\n[bot]\nllm_preflight_check = true\n")

    _enforce_headless_config(config)

    rendered = config.read_text(encoding="utf-8")
    assert "enable_http_router = false" in rendered
    assert "llm_preflight_check = false" in rendered
    assert "enable_watchdog = false" in rendered
    assert "[plugin_deps]" in rendered
    assert "enabled = false" in rendered
    assert "[plugin_market]" in rendered


def test_mofox_reports_the_pinned_upstream_requirement_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_distribution(_name: str) -> None:
        raise PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "distribution", missing_distribution)
    with pytest.raises(RuntimeError, match="e2ee2ff73b494428bbdfd983c7569c6f074a9c76"):
        _install_upstream_namespace()


def test_mofox_workspace_is_explicit_and_projection_options_are_rejected(tmp_path: Path) -> None:
    settings = AppSettings(core={"data_dir": tmp_path / "data"})  # type: ignore[arg-type]
    workspace = _workspace_path(settings, "mofox", {"workspace": str(tmp_path / "isolated")})
    assert workspace == (tmp_path / "isolated").resolve()
    assert workspace != settings.core.data_dir.resolve()
    with pytest.raises(RuntimeError, match="migration_required"):
        _validate_bridge_settings("limited", ("onebot.*.message.*",), (), {"projection_mode": "copy"})


def test_mofox_engine_restores_working_directory() -> None:
    engine = MoFoxHeadlessEngine(Path("state"), {})
    original = Path.cwd()
    engine._previous_cwd = original
    engine._restore_working_directory()
    assert Path.cwd() == original
    assert engine._previous_cwd is None


def _write_bridge_plugin(root: Path) -> None:
    plugin = root / "plugins" / "liteyuki_bridge_probe"
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text(
        """{
  "name": "liteyuki_bridge_probe",
  "version": "1.0.0",
  "description": "Liteyuki bridge verification plugin",
  "author": "LiteyukiBot",
  "dependencies": {"plugins": [], "components": []},
  "entry_point": "plugin.py",
  "python_dependencies": []
}
""",
        encoding="utf-8",
    )
    (plugin / "plugin.py").write_text(
        "from src.core.components import BaseEventHandler, BasePlugin, EventType\n"
        "from src.core.components.loader import register_plugin\n"
        "from src.core.models.message import Message\n"
        "from src.core.transport.message_send import get_message_sender\n"
        "from src.kernel.event import EventDecision\n\n"
        "class ReplyHandler(BaseEventHandler):\n"
        "    name = 'reply'\n"
        "    init_subscribe = [EventType.ON_MESSAGE_RECEIVED]\n\n"
        "    async def execute(self, _event_name, params):\n"
        "        message = params['message']\n"
        "        if message.processed_plain_text == '/bridge_probe':\n"
        "            await get_message_sender().send_message(Message(\n"
        "                message_id='bridge-reply', content='mofox bridge reply',\n"
        "                processed_plain_text='mofox bridge reply', platform=message.platform,\n"
        "                chat_type=message.chat_type, stream_id=message.stream_id,\n"
        "            ), adapter_signature='liteyuki:adapter:injected')\n"
        "        return EventDecision.SUCCESS, params\n\n"
        "@register_plugin\n"
        "class BridgePlugin(BasePlugin):\n"
        "    plugin_name = 'liteyuki_bridge_probe'\n"
        "    plugin_description = 'Bridge verification'\n"
        "    plugin_version = '1.0.0'\n\n"
        "    def get_components(self):\n"
        "        return [ReplyHandler]\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
@pytest.mark.skipif(not _has_upstream_runtime(), reason="requires the pinned Neo-MoFox upstream runtime")
async def test_mofox_upstream_receiver_routes_workspace_plugin_reply(tmp_path: Path) -> None:
    _write_bridge_plugin(tmp_path)
    engine = MoFoxHeadlessEngine(tmp_path, {})
    sent: list[Message] = []

    async def emit(message: Message) -> None:
        sent.append(message)

    event = _event().model_copy(
        update={"message": Message(segments=(Segment(type="text", data={"text": "/bridge_probe"}),))}
    )
    try:
        await engine.start()
        await engine.process(event, emit)
    finally:
        await engine.close()

    assert sent == [Message(segments=(Segment(type="text", data={"text": "mofox bridge reply"}),))]


class _FakeRunner:
    def __init__(self, success: bool) -> None:
        self.success = success
        self.actions: list[dict[str, object]] = []

    async def request_action(self, **request: object) -> ActionResult:
        self.actions.append(request)
        return ActionResult(
            action_id="action-1",
            success=self.success,
            payload=None if self.success else {"error": "failed"},
        )


class _FakeEngine:
    async def process(self, event: EventEnvelope, sink: Callable[[Message], Awaitable[None]]) -> None:
        assert event.id == "event-1"
        await sink(Message(segments=(Segment(type="text", data={"text": "MoFox response"}),)))


@pytest.mark.asyncio
async def test_mofox_bridge_returns_ordered_output_to_source_action() -> None:
    runner = _FakeRunner(True)
    host = MoFoxBridgeHost(_FakeEngine(), max_concurrent_events=1)  # type: ignore[arg-type]

    await host.handle_delivery(_delivery(runner, _event()))

    assert len(runner.actions) == 1
    assert runner.actions[0]["kind"] == "message.send"
    assert runner.actions[0]["resource_key"] == "bot:nonebot:bot-1"
    assert runner.actions[0]["payload"]["message"]["segments"][0]["data"]["text"] == "MoFox response"  # type: ignore[index]


@pytest.mark.asyncio
async def test_mofox_bridge_propagates_source_action_failure() -> None:
    runner = _FakeRunner(False)
    host = MoFoxBridgeHost(_FakeEngine(), max_concurrent_events=1)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="source bridge rejected"):
        await host.handle_delivery(_delivery(runner, _event()))
