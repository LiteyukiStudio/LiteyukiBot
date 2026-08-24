from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from liteyuki.bot import _install_runtime, _reset_runtime
from liteyuki.session import (
    Matcher,
    MessageEvent,
    Rule,
    Scene,
    SceneType,
    Session,
    User,
    is_su_rule,
    on_endswith,
    on_fullmatch,
    on_keywords,
    on_message,
    on_startswith,
)
from liteyuki.session.message import BaseSeg, Image, Text
from liteyuki.session.on import _dispatch_matchers, _reset_matchers, get_matchers

from liteyukibot.exceptions import LegacyUnsupportedError


@pytest.fixture(autouse=True)
def reset_matchers() -> Iterator[None]:
    _reset_matchers()
    yield
    _reset_matchers()


def _event(raw_message: str = "hello", *, user_id: str = "user") -> MessageEvent:
    return MessageEvent(
        bot_id="bot",
        message=raw_message,
        message_type="message",
        raw_message=raw_message,
        session_id="conversation",
        user_id=user_id,
        session_type="group",
        data={"source": "fixture"},
    )


def test_message_event_preserves_attributes_and_ordered_replies() -> None:
    event = _event()

    event.reply("first")
    event.reply({"type": "text", "data": {"text": "second"}})

    assert event.bot_id == "bot"
    assert event.raw_message == "hello"
    assert event.data == {"source": "fixture"}
    assert event.replies == (
        "first",
        {"type": "text", "data": {"text": "second"}},
    )
    assert event._drain_replies() == (
        "first",
        {"type": "text", "data": {"text": "second"}},
    )
    assert not event.replies


def test_message_event_rejects_receive_channel() -> None:
    with pytest.raises(LegacyUnsupportedError, match="Channel semantics"):
        MessageEvent(
            bot_id="bot",
            message="hello",
            message_type="message",
            raw_message="hello",
            session_id="conversation",
            user_id="user",
            session_type="group",
            receive_channel=object(),
        )


def test_matcher_registration_validates_inputs_and_can_reset() -> None:
    on_message()
    assert len(get_matchers()) == 1
    _reset_matchers()
    assert get_matchers() == ()

    with pytest.raises(ValueError, match="non-empty strings"):
        on_keywords([])
    with pytest.raises(ValueError, match="non-negative"):
        on_message(priority=-1)


@pytest.mark.asyncio
async def test_rule_supports_sync_async_and_short_circuit_composition() -> None:
    calls: list[str] = []

    @Rule
    def sync_false(_event: MessageEvent) -> bool:
        calls.append("sync")
        return False

    @Rule
    async def async_true(_event: MessageEvent) -> bool:
        calls.append("async")
        return True

    event = _event()
    assert await (sync_false & async_true)(event) is False
    assert calls == ["sync"]
    calls.clear()
    assert await (sync_false | async_true)(event) is True
    assert calls == ["sync", "async"]
    assert await (~async_true)(event) is False


@pytest.mark.asyncio
async def test_superuser_rule_reads_runtime_configuration() -> None:
    _install_runtime({"liteyuki.superusers": ["admin"]}, lambda _name: None)
    try:
        assert await is_su_rule(_event(user_id="admin")) is True
        assert await is_su_rule(_event(user_id="user")) is False
    finally:
        _reset_runtime()


@pytest.mark.asyncio
async def test_matcher_priority_and_match_aware_blocking() -> None:
    calls: list[str] = []

    @on_fullmatch("never", priority=20, block=True).handle()
    async def unmatched(_event: MessageEvent) -> None:
        calls.append("unmatched")

    @on_message(priority=10, block=True).handle()
    async def first(_event: MessageEvent) -> None:
        calls.append("first")

    @on_message(priority=10).handle()
    def same_priority(_event: MessageEvent) -> None:
        calls.append("same")

    @on_message(priority=5).handle()
    async def lower(_event: MessageEvent) -> None:
        calls.append("lower")

    result = await _dispatch_matchers(_event())

    assert [matcher.priority for matcher in get_matchers()] == [20, 10, 10, 5]
    assert calls == ["first", "same"]
    assert result.matched == 2
    assert result.handlers_called == 2
    assert result.blocked is True


@pytest.mark.asyncio
async def test_matcher_isolates_handler_failure_and_continues() -> None:
    matcher = on_message()

    @matcher.handle()
    def broken(_event: MessageEvent) -> None:
        raise RuntimeError("broken handler")

    @matcher.handle()
    async def working(event: MessageEvent) -> None:
        event.reply("handled")

    event = _event()
    result = await _dispatch_matchers(event)

    assert result.handlers_called == 2
    assert len(result.failures) == 1
    assert "broken handler" in result.failures[0]
    assert event.replies == ("handled",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("register", "raw_message", "matches"),
    [
        (lambda: on_keywords(["ell"]), "hello", True),
        (lambda: on_startswith(["he"]), "hello", True),
        (lambda: on_endswith(["lo"]), "hello", True),
        (lambda: on_fullmatch(["hello"]), "hello", True),
        (lambda: on_fullmatch(["other"]), "hello", False),
    ],
)
async def test_on_predicates(
    register: Callable[[], Matcher],
    raw_message: str,
    matches: bool,
) -> None:
    matcher = register()

    assert (await matcher.run(_event(raw_message))).matched is matches


@pytest.mark.asyncio
async def test_representative_v6_plugin_imports_and_registers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = "legacy_session_fixture"
    (tmp_path / f"{module_name}.py").write_text(
        """
from liteyuki.session.event import MessageEvent
from liteyuki.session.on import on_startswith

@on_startswith(["liteecho"]).handle()
async def echo(event: MessageEvent):
    event.reply(event.raw_message.removeprefix("liteecho").strip())
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        importlib.import_module(module_name)
        event = _event("liteecho hello")
        result = await _dispatch_matchers(event)
    finally:
        sys.modules.pop(module_name, None)

    assert result.matched == 1
    assert event.replies == ("hello",)


def test_session_identity_and_basic_segments() -> None:
    user = User(id="user")
    private = Session(
        self_id="bot",
        adapter="onebot",
        scope=SceneType.PRIVATE,
        scene=Scene(id="user", type=SceneType.PRIVATE),
        user=user,
    )
    group = Session(
        self_id="bot",
        adapter="onebot",
        scope=SceneType.GROUP,
        scene=Scene(id="group", type=SceneType.GROUP),
        user=user,
    )

    assert private.session_id == "0:user"
    assert private.target_id == "0:user"
    assert group.session_id == "1:group"
    assert group.target_id == "1:group:user"
    assert BaseSeg(data={"value": 1}).type == "Segment"
    assert Text(data={}, content="hello").content == "hello"
    assert Image(data={}, url="https://example.invalid/image.png").url.endswith("image.png")
