from __future__ import annotations

import asyncio
import importlib.metadata
from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest
from liteyukibot_runtime_mofox.host import (
    MoFoxHeadlessEngine,
    MoFoxRuntimeHost,
    _enforce_headless_config,
    _install_upstream_namespace,
)
from liteyukibot_runtime_mofox.translate import to_mofox_envelope, to_mofox_event_input, to_send_action

from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope, Message, Segment, SendMessage
from liteyukibot.runtime.protocol import ActionResponse, EventAccepted, EventCompleted, EventMessage


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


def test_mofox_translation_preserves_source_identity_and_wire_route() -> None:
    event = _event()

    translated = to_mofox_event_input(event)
    envelope = to_mofox_envelope(translated)
    action = to_send_action(event, "response")

    assert translated.runtime_id == "nonebot"
    assert envelope["message_info"]["group_info"]["group_id"] == "group-1"
    assert envelope["message_segment"] == [{"type": "text", "data": "hello"}]
    assert action.runtime_id == "nonebot"
    assert action.event_id == "event-1"
    assert isinstance(action.action, SendMessage)
    assert action.action.reply_token == "reply-1"


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


def test_mofox_engine_restores_working_directory() -> None:
    engine = MoFoxHeadlessEngine(Path("state"), {})
    original = Path.cwd()
    engine._previous_cwd = original

    engine._restore_working_directory()

    assert Path.cwd() == original
    assert engine._previous_cwd is None


def _write_bridge_plugin(root: Path) -> None:
    plugin = root / "mofox" / "plugins" / "liteyuki_bridge_probe"
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
async def test_mofox_upstream_receiver_routes_a_managed_plugin_reply(tmp_path: Path) -> None:
    """Exercise the pinned Neo-MoFox receiver and plugin loader."""

    _write_bridge_plugin(tmp_path)
    engine = MoFoxHeadlessEngine(tmp_path, {})
    sent: list[str] = []

    async def emit(text: str) -> None:
        sent.append(text)

    event = _event().model_copy(
        update={"message": Message(segments=(Segment(type="text", data={"text": "/bridge_probe"}),))}
    )
    try:
        await engine.start()
        await engine.process(event, emit)
    finally:
        await engine.close()

    assert sent == ["mofox bridge reply"]


class FakeClient:
    def __init__(self) -> None:
        self.sent: list[object] = []
        self.actions: list[dict[str, object]] = []

    async def send(self, message: object) -> None:
        self.sent.append(message)

    async def execute_action(
        self,
        _correlation_id: str,
        payload: dict[str, object],
        *,
        delivery_correlation_id: str | None = None,
    ) -> ActionResponse:
        assert delivery_correlation_id == "delivery-1"
        self.actions.append(payload)
        return ActionResponse(correlation_id="action", ok=True)


class FakeEngine:
    async def process(self, event: EventEnvelope, sink: Callable[[str], Awaitable[None]]) -> None:
        assert event.id == "event-1"
        await sink("MoFox response")

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_mofox_host_returns_chatter_output_to_the_source_runtime() -> None:
    client = FakeClient()
    host = MoFoxRuntimeHost(client, FakeEngine(), max_concurrent_events=1)  # type: ignore[arg-type]
    event = _event()

    await host._accept_event(EventMessage(correlation_id="delivery-1", payload=event.model_dump(mode="json")))
    await asyncio.gather(*host._tasks)
    await host.close()

    assert client.sent == [
        EventAccepted(correlation_id="delivery-1", status="accepted"),
        EventCompleted(correlation_id="delivery-1", status="completed"),
    ]
    assert client.actions[0]["runtime_id"] == "nonebot"
    assert client.actions[0]["event_id"] == "event-1"
