from __future__ import annotations

from collections.abc import Mapping

import pytest
from liteyukibot_runtime_nonebot_api import NoneBotBotProxy, NoneBotEventProxy

from liteyukibot import AuthorizationContext, RuntimeBinding, RuntimeCallContext
from liteyukibot.events import ConversationRef, EventEnvelope, JsonValue, Message, Segment


def _context() -> RuntimeCallContext:
    event = EventEnvelope(
        runtime_id="nonebot",
        adapter="onebot-v11",
        bot_id="bot-1",
        type="message.created",
        conversation=ConversationRef(id="chat-1", type="group"),
    )
    return RuntimeCallContext("example.plugin", event, AuthorizationContext(event.id, "nonebot", "bot-1"))


@pytest.mark.asyncio
async def test_typed_nonebot_facades_map_portable_event_and_bot_operations() -> None:
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
                    "runtime_id": "nonebot",
                    "adapter": "onebot-v11",
                    "bot_id": "bot-1",
                    "event_type": "message.created",
                    "conversation": {"id": "chat-1", "type": "group"},
                    "actor": None,
                    "message": None,
                }
            if binding.api == "bot" and operation == "snapshot":
                return {"bot_id": "bot-1", "adapter": "onebot-v11", "capabilities": ()}
            assert operation == "send"
            assert "message" in arguments or "conversation" in arguments
            return {"sent": True}

    event = NoneBotEventProxy(
        RuntimeBinding("nonebot", "event", "^1.0", False, "nonebot"),
        Backend(),
        _context(),
    )
    snapshot = await event.snapshot()
    sent = await event.send(Message(segments=(Segment(type="text", data={"text": "hello"}),)))

    bot = NoneBotBotProxy(
        RuntimeBinding("nonebot", "bot", "^1.0", False, "nonebot_bot"),
        Backend(),
        _context(),
    )
    bot_snapshot = await bot.snapshot()
    proactive = await bot.send(
        Message(segments=(Segment(type="text", data={"text": "hello"}),)),
        ConversationRef(id="chat-1", type="group"),
    )

    assert snapshot.adapter == "onebot-v11"
    assert sent == {"sent": True}
    assert bot_snapshot.bot_id == "bot-1"
    assert proactive == {"sent": True}
