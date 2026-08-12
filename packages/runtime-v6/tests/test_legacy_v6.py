from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

import liteyuki
import pytest
from _support import FakeLogger
from liteyuki import LiteyukiBot, get_bot, get_config
from liteyuki.bot import _emit_lifecycle, _install_runtime, _reset_runtime

from liteyukibot.events import (
    ActionEnvelope,
    ActorRef,
    ConversationRef,
    EventEnvelope,
    Message,
    Segment,
    SendMessage,
)
from liteyukibot.exceptions import LegacyUnsupportedError
from liteyukibot.runtime import ActionProvenance, ActionSinkResult, RuntimeSpec, RuntimeSupervisor


def test_v6_compatibility_namespace_uses_kernel_version() -> None:
    assert importlib.metadata.version("liteyukibot-v7") == liteyuki.__version__


def test_legacy_context_and_unsupported_nested_host() -> None:
    calls: list[str] = []
    _install_runtime({"name": "legacy"}, lambda name: calls.append(name or "all"))
    try:
        bot = get_bot()

        @bot.on_before_start
        async def before_start() -> None:
            calls.append("before")

        assert get_config("name") == "legacy"
        bot.restart_process("worker")
        import asyncio

        asyncio.run(_emit_lifecycle("before_start"))
        assert calls == ["worker", "before"]
        with pytest.raises(LegacyUnsupportedError, match="nested"):
            LiteyukiBot()
    finally:
        _reset_runtime()


def test_unsupported_v6_channel_raises_migration_error() -> None:
    with pytest.raises(LegacyUnsupportedError, match="comm.channel.get_channel"):
        from liteyuki.comm.channel import get_channel  # noqa: F401


@pytest.mark.asyncio
async def test_v6_runtime_loads_plugin_and_runs_lifecycle(tmp_path: Path) -> None:
    plugin = tmp_path / "legacy_fixture.py"
    plugin.write_text(
        """
from pathlib import Path
from liteyuki import PluginMetadata, get_bot

__plugin_meta__ = PluginMetadata(name="Legacy Fixture")
bot = get_bot()

@bot.on_before_start
async def before_start():
    Path("started.txt").write_text("started", encoding="utf-8")

@bot.on_after_shutdown
async def after_shutdown():
    Path("stopped.txt").write_text("stopped", encoding="utf-8")
""".lstrip(),
        encoding="utf-8",
    )
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    supervisor.add(
        RuntimeSpec(
            id="legacy",
            kind="v6",
            options={"config": {"answer": 42}, "plugins": ["legacy_fixture"]},
            working_directory=tmp_path,
            ready_timeout=5,
            heartbeat_interval=0.05,
            stale_after=1,
        )
    )

    await supervisor.start()
    assert (tmp_path / "started.txt").read_text(encoding="utf-8") == "started"
    await supervisor.stop()
    assert (tmp_path / "stopped.txt").read_text(encoding="utf-8") == "stopped"


@pytest.mark.asyncio
async def test_v6_runtime_dispatches_matchers_and_returns_ordered_reply_actions(
    tmp_path: Path,
) -> None:
    plugin = tmp_path / "legacy_echo_fixture.py"
    plugin.write_text(
        """
from liteyuki.session.event import MessageEvent
from liteyuki.session.on import on_startswith

@on_startswith("liteecho").handle()
async def echo(event: MessageEvent):
    event.reply(event.raw_message.removeprefix("liteecho").strip())
    event.reply({"type": "image", "data": {"url": "https://example.invalid/reply.png"}})
""".lstrip(),
        encoding="utf-8",
    )
    actions: list[ActionEnvelope] = []

    async def execute_action(
        source_runtime_id: str,
        payload: dict[str, Any],
        _provenance: ActionProvenance | None,
    ) -> ActionSinkResult:
        assert source_runtime_id == "legacy"
        action = ActionEnvelope.model_validate(payload)
        actions.append(action)
        if len(actions) == 1:
            return ActionSinkResult(ok=False, error="fixture failure")
        return ActionSinkResult(ok=True, data={"message_id": "sent-2"})

    supervisor = RuntimeSupervisor(
        logger=FakeLogger(),
        action_sink=execute_action,
    )
    supervisor.add(
        RuntimeSpec(
            id="legacy",
            kind="v6",
            options={"plugins": ["legacy_echo_fixture"]},
            working_directory=tmp_path,
            ready_timeout=5,
            heartbeat_interval=0.05,
            stale_after=1,
        )
    )
    envelope = EventEnvelope(
        id="event-1",
        runtime_id="adapter",
        adapter="onebot-v11",
        bot_id="bot-1",
        type="message.group.normal",
        conversation=ConversationRef(id="group-1", type="group"),
        actor=ActorRef(id="user-1"),
        message=Message(segments=(Segment(type="text", data={"text": "liteecho hello"}),)),
        reply_token="reply-token",
        raw={"message_id": 42},
    )

    await supervisor.start()
    try:
        record = supervisor.records["legacy"]
        assert "runtime.events.receive" in record.capabilities
        assert "runtime.actions.send" in record.capabilities

        accepted = await supervisor.dispatch_event(
            "legacy",
            "delivery-1",
            envelope.model_dump(mode="json"),
            timeout_seconds=5,
        )
    finally:
        await supervisor.stop()

    assert accepted.status == "accepted"
    assert len(actions) == 2
    first, second = actions
    assert first.event_id == second.event_id == "event-1"
    assert first.runtime_id == second.runtime_id == "adapter"
    assert first.bot_id == second.bot_id == "bot-1"
    assert isinstance(first.action, SendMessage)
    assert isinstance(second.action, SendMessage)
    assert first.action.message.plain_text == "hello"
    assert first.action.reply_token == second.action.reply_token == "reply-token"
    assert second.action.message.segments[0] == Segment(
        type="adapter",
        data={
            "type": "image",
            "data": {"url": "https://example.invalid/reply.png"},
        },
    )
