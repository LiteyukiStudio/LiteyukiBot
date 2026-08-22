from __future__ import annotations

from collections.abc import Mapping

import pytest
from liteyukibot_runtime_nonebot_api import NoneBotBotProxy, NoneBotEventProxy

from liteyukibot import AuthorizationContext, RuntimeApiError, RuntimeBinding, RuntimeCallContext
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
                    "source_event_id": "v1:nonebot:onebot-v11:bot-1:event-1",
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
    assert sent.sent is True
    assert bot_snapshot.bot_id == "bot-1"
    assert proactive.sent is True


@pytest.mark.asyncio
async def test_nonebot_send_rejects_an_invalid_canonical_result() -> None:
    class Backend:
        async def invoke(
            self,
            _binding: RuntimeBinding,
            _operation: str,
            _arguments: Mapping[str, JsonValue],
            _context: RuntimeCallContext,
        ) -> JsonValue:
            return {}

    proxy = NoneBotEventProxy(
        RuntimeBinding("nonebot", "event", "^1.2", False, "nonebot"),
        Backend(),
        _context(),
    )

    with pytest.raises(RuntimeApiError, match="RUNTIME_API_INVALID_RESULT"):
        await proxy.send("hello")
