from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from liteyukibot_runtime_astrbot.host import (
    AstrBotHeadlessEngine,
    AstrBotLogBridge,
    AstrBotRuntimeHost,
    _dispose_astrbot_global_database,
    _restore_child_logging,
)
from liteyukibot_runtime_astrbot.translate import to_astr_event_input, to_send_action

from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope, Message, Segment, SendMessage
from liteyukibot.runtime.protocol import ActionResponse, EventAccepted, EventCompleted, EventMessage


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


def test_astrbot_translation_preserves_source_identity_and_message_route() -> None:
    event = _event()

    translated = to_astr_event_input(event)
    action = to_send_action(event, "response")

    assert translated.runtime_id == "nonebot"
    assert translated.conversation_type == "group"
    assert translated.actor_id == "user-1"
    assert translated.text == "hello"
    assert action.runtime_id == "nonebot"
    assert action.event_id == "event-1"
    assert isinstance(action.action, SendMessage)
    assert action.action.reply_token == "reply-1"


def test_astrbot_translation_rejects_non_message_events() -> None:
    event = _event().model_copy(update={"message": None})

    with pytest.raises(ValueError, match="message events"):
        to_astr_event_input(event)


def _write_bridge_plugin(root: Path) -> None:
    plugin = root / "astrbot" / "data" / "plugins" / "liteyuki_bridge_probe"
    plugin.mkdir(parents=True)
    (plugin / "metadata.yaml").write_text(
        "name: liteyuki_bridge_probe\n"
        "description: Liteyuki bridge verification plugin\n"
        "version: 1.0.0\n"
        "author: LiteyukiBot\n",
        encoding="utf-8",
    )
    (plugin / "main.py").write_text(
        "from astrbot.api import star\n"
        "from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter\n\n"
        "@star.register('liteyuki_bridge_probe', 'LiteyukiBot', 'Bridge verification', '1.0.0')\n"
        "class Main(star.Star):\n"
        "    @filter.command('bridge_probe')\n"
        "    async def bridge_probe(self, event: AstrMessageEvent) -> None:\n"
        "        event.set_result(MessageEventResult().message('astrbot bridge reply'))\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_astrbot_upstream_pipeline_routes_a_managed_plugin_reply(tmp_path: Path) -> None:
    """Exercise the installed AstrBot scheduler, not a substitute engine."""

    _write_bridge_plugin(tmp_path)
    logger = RecordingCleanupLogger()
    engine = AstrBotHeadlessEngine(tmp_path, {}, logger)
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

    assert sent == ["astrbot bridge reply"]


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
        await sink("AstrBot response")

    async def close(self) -> None:
        return None


class RecordingLogger:
    def __init__(self, records: list[tuple[dict[str, object], str, str]] | None = None, **fields: object) -> None:
        self.records = records if records is not None else []
        self.fields = fields

    def bind(self, **fields: object) -> RecordingLogger:
        return RecordingLogger(self.records, **self.fields, **fields)

    def info(self, _format: str, message: str) -> None:
        self.records.append((self.fields, "INFO", message))

    def warning(self, _format: str, message: str) -> None:
        self.records.append((self.fields, "WARNING", message))


class FakeBroker:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[object] = asyncio.Queue()
        self.unregistered = False

    def register(self) -> asyncio.Queue[object]:
        return self.queue

    def unregister(self, _queue: object) -> None:
        self.unregistered = True


class FakeLogManager:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def set_queue_handler(self, logger: object, broker: object) -> None:
        self.calls.append((logger, broker))


class FakeEngineLifecycle:
    def __init__(self) -> None:
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class RecordingCleanupLogger:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, object]] = []

    def warning(self, message: str, error: object) -> None:
        self.warnings.append((message, error))


@pytest.mark.asyncio
async def test_astrbot_host_returns_pipeline_output_to_the_source_runtime() -> None:
    client = FakeClient()
    host = AstrBotRuntimeHost(client, FakeEngine(), max_concurrent_events=1)  # type: ignore[arg-type]
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


@pytest.mark.asyncio
async def test_astrbot_log_bridge_forwards_public_broker_records() -> None:
    broker = FakeBroker()
    logger = RecordingLogger()
    manager = FakeLogManager()
    bridge = AstrBotLogBridge(broker, logger)

    bridge.start(manager, "astrbot")
    await broker.queue.put({"level": "WARNING", "data": "upstream warning", "category": "plugin"})
    await asyncio.sleep(0)
    await bridge.close()

    assert manager.calls == [("astrbot", broker)]
    assert logger.records == [({"upstream": "astrbot", "upstream_category": "plugin"}, "WARNING", "upstream warning")]
    assert broker.unregistered is True


def test_astrbot_restores_child_logging_after_upstream_initialization(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[str] = []
    monkeypatch.setattr("liteyukibot_runtime_astrbot.host.shutdown_logging", lambda: observed.append("shutdown"))
    monkeypatch.setattr(
        "liteyukibot_runtime_astrbot.host.configure_runtime_child_logging",
        lambda: observed.append("configure"),
    )

    _restore_child_logging()

    assert observed == ["shutdown", "configure"]


@pytest.mark.asyncio
async def test_astrbot_engine_close_releases_global_database_after_lifecycle_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed: list[str] = []
    lifecycle = FakeEngineLifecycle()
    engine = AstrBotHeadlessEngine(tmp_path, {}, RecordingCleanupLogger())
    engine._lifecycle = lifecycle
    async def dispose(_logger: object) -> None:
        observed.append("dispose")

    monkeypatch.setattr("liteyukibot_runtime_astrbot.host._dispose_astrbot_global_database", dispose)

    await engine.close()

    assert lifecycle.stopped is True
    assert observed == ["dispose"]


@pytest.mark.asyncio
async def test_astrbot_global_database_cleanup_absorbs_upstream_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = RecordingCleanupLogger()

    def unavailable(_name: str) -> object:
        raise RuntimeError("not installed")

    monkeypatch.setattr("liteyukibot_runtime_astrbot.host.import_module", unavailable)
    await _dispose_astrbot_global_database(logger)

    assert len(logger.warnings) == 1
    message, error = logger.warnings[0]
    assert message == "AstrBot global database cleanup failed: {}"
    assert isinstance(error, RuntimeError)
    assert str(error) == "not installed"
