"""Minimal installable LiteyukiBot v7 native plugin."""

from __future__ import annotations

from liteyukibot import PluginContext, PluginDefinition, PluginHandle, PluginManifest
from liteyukibot.events import (
    ActionEnvelope,
    EventEnvelope,
    HandlerResult,
    Message,
    Segment,
    SendMessage,
)


async def setup(context: PluginContext) -> PluginHandle:
    prefix = context.config.get("prefix", "echo: ")
    if not isinstance(prefix, str):
        raise TypeError("example.echo config prefix must be a string")

    async def echo(event: EventEnvelope) -> HandlerResult | None:
        if event.message is None:
            return None
        reply = Message(segments=(Segment(type="text", data={"text": prefix + event.message.plain_text}),))
        action = ActionEnvelope(
            event_id=event.id,
            runtime_id=event.runtime_id,
            bot_id=event.bot_id,
            action=SendMessage(
                message=reply,
                conversation=event.conversation,
                reply_token=event.reply_token,
            ),
        )
        return HandlerResult(actions=(action,))

    subscription = context.events.subscribe(echo, name="example.echo")

    async def stop() -> None:
        context.events.unsubscribe(subscription)

    return PluginHandle(stop=stop)


plugin = PluginDefinition(
    manifest=PluginManifest(
        id="example.echo",
        name="Echo example",
        version="0.1.0",
        storage="private",
    ),
    setup=setup,
)

__all__ = ["plugin"]
