from __future__ import annotations

from collections.abc import Mapping

import pytest
from liteyukibot_runtime_astrbot_api import AstrBotBotProxy, AstrBotEventProxy

from liteyukibot import AuthorizationContext, RuntimeBinding, RuntimeCallContext
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
                    "platform_id": "onebot",
                    "platform_name": "qq",
                    "bot_id": "bot-1",
                    "session_id": "chat-1",
                    "message": "hello",
                    "message_type": "group",
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
                    "platform_id": "qq",
                    "platform_name": "aiocqhttp",
                    "capabilities": (),
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
    assert sent == {"sent": True}
    assert portable == {"sent": True}
    assert bot_snapshot.platform_name == "aiocqhttp"
    assert proactive == {"sent": True}
