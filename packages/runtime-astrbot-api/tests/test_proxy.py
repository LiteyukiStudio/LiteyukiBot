from __future__ import annotations

from collections.abc import Mapping

import pytest
from liteyukibot_runtime_astrbot_api import AstrBotEventProxy

from liteyukibot import AuthorizationContext, RuntimeBinding, RuntimeCallContext
from liteyukibot.events import ConversationRef, EventEnvelope, JsonValue


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
async def test_typed_event_proxy_maps_alpha8_operations() -> None:
    class Backend:
        async def invoke(
            self,
            _binding: RuntimeBinding,
            operation: str,
            arguments: Mapping[str, JsonValue],
            _context: RuntimeCallContext,
        ) -> JsonValue:
            if operation == "snapshot":
                return {
                    "platform_id": "onebot",
                    "platform_name": "qq",
                    "bot_id": "bot-1",
                    "session_id": "chat-1",
                    "message": "hello",
                    "message_type": "group",
                }
            assert arguments == {"message": "pong"}
            return {"sent": True}

    proxy = AstrBotEventProxy(
        RuntimeBinding("astrbot", "event", "^1.0", False, "astrbot"),
        Backend(),
        _context(),
    )
    snapshot = await proxy.snapshot()
    sent = await proxy.send("pong")

    assert snapshot.session_id == "chat-1"
    assert sent == {"sent": True}
