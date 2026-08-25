from __future__ import annotations

from collections.abc import Mapping

import pytest
from liteyukibot_runtime_astrbot_api import AstrBotBotProxy, AstrBotEventProxy

from liteyukibot import AuthorizationContext, RuntimeApiError, RuntimeBinding, RuntimeCallContext
from liteyukibot.events import ConversationRef, EventEnvelope, JsonValue, Message, Segment


def _context() -> RuntimeCallContext:
    event = EventEnvelope(
        runtime_id="astrbot",
        adapter="qq",
        bot_id="bot-1",
        type="message.created",
        conversation=ConversationRef(id="chat-1", type="group"),
    )
    return RuntimeCallContext("example.plugin", event, AuthorizationContext(event.id, "astrbot", "bot-1"))


@pytest.mark.asyncio
async def test_typed_event_proxy_maps_alpha9_operations() -> None:
    class Backend:
        async def invoke(
            self,
            binding: RuntimeBinding,
            operation: str,
            arguments: Mapping[str, JsonValue],
            _context: RuntimeCallContext,
        ) -> JsonValue:
            if binding.api == "event" and operation == "snapshot":
                return {
                    "source_event_id": "v1:astrbot:onebot:bot-1:event-1",
                    "runtime_id": "astrbot",
                    "adapter": "aiocqhttp",
                    "bot_id": "bot-1",
                    "event_type": "message.created",
                    "conversation": {"id": "chat-1", "type": "group"},
                    "extensions": {
                        "astrbot": {
                            "platform_id": "onebot",
                            "platform_name": "qq",
                            "session_id": "chat-1",
                            "message_type": "group",
                        }
                    },
                }
            if binding.api == "event":
                assert arguments in (
                    {"message": "pong"},
                    {"message": {"segments": [{"type": "text", "data": {"text": "portable"}}]}},
                )
                return {"sent": True}
            if operation == "snapshot":
                assert arguments == {}
                return {
                    "bot_id": "bot-1",
                    "adapter": "aiocqhttp",
                    "extensions": {"astrbot": {"platform_id": "qq", "platform_name": "aiocqhttp"}},
                }
            assert arguments == {
                "message": {"segments": [{"type": "text", "data": {"text": "proactive"}}]},
                "conversation": {"id": "chat-1", "type": "group", "parent_id": None},
            }
            return {"sent": True}

    proxy = AstrBotEventProxy(
        RuntimeBinding("astrbot", "event", "^1.0", False, "astrbot"),
        Backend(),
        _context(),
    )
    snapshot = await proxy.snapshot()
    sent = await proxy.send("pong")
    portable = await proxy.send_message(Message(segments=(Segment(type="text", data={"text": "portable"}),)))

    bot = AstrBotBotProxy(
        RuntimeBinding("astrbot", "bot", "^1.0", False, "astrbot_bot"),
        Backend(),
        _context(),
    )
    bot_snapshot = await bot.snapshot()
    proactive = await bot.send(
        Message(segments=(Segment(type="text", data={"text": "proactive"}),)),
        ConversationRef(id="chat-1", type="group"),
    )

    assert snapshot.session_id == "chat-1"
    assert sent.sent is True
    assert portable.sent is True
    assert bot_snapshot.platform_name == "aiocqhttp"
    assert proactive.sent is True


@pytest.mark.asyncio
async def test_astrbot_send_rejects_an_invalid_canonical_result() -> None:
    class Backend:
        async def invoke(
            self,
            _binding: RuntimeBinding,
            _operation: str,
            _arguments: Mapping[str, JsonValue],
            _context: RuntimeCallContext,
        ) -> JsonValue:
            return {}

    proxy = AstrBotEventProxy(
        RuntimeBinding("astrbot", "event", "^1.2", False, "astrbot"),
        Backend(),
        _context(),
    )

    with pytest.raises(RuntimeApiError, match="RUNTIME_API_INVALID_RESULT"):
        await proxy.send("hello")
