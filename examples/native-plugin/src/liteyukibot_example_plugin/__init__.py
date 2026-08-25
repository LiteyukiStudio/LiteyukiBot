"""Minimal installable LiteyukiBot v7 native plugin."""

from __future__ import annotations

from typing import Any

from liteyukibot import PluginContext, PluginDefinition, PluginManifest, RuntimeRequirement, RuntimeUnavailable, runtime
from liteyukibot.events import (
    ActionEnvelope,
    EventEnvelope,
    HandlerResult,
    Message,
    Segment,
    SendMessage,
)


@runtime("nonebot", api="event", version="^1.2", optional=True, as_="nonebot")
async def observe_provider_event(event: EventEnvelope, *, nonebot: Any) -> HandlerResult | None:
    if not getattr(nonebot, "available", False):
        return None
    snapshot = getattr(nonebot, "snapshot", None)
    if not callable(snapshot):
        return None
    try:
        await snapshot()
    except RuntimeUnavailable:
        return None
    return None


async def setup(context: PluginContext) -> None:
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

    context.defer_cleanup(lambda: context.events.unsubscribe(subscription))


async def setup_runtime_facade(context: PluginContext) -> None:
    subscription = context.events.subscribe(observe_provider_event, name="example.runtime_probe")
    context.defer_cleanup(lambda: context.events.unsubscribe(subscription))


plugin = PluginDefinition(
    manifest=PluginManifest(
        id="example.echo",
        name="Echo example",
        version="0.1.0",
        storage="private",
    ),
    setup=setup,
)

runtime_facade_plugin = PluginDefinition(
    manifest=PluginManifest(
        id="example.runtime",
        name="Runtime facade example",
        version="0.1.0",
        runtime_requirements=(
            RuntimeRequirement(
                runtime="nonebot",
                api="event",
                version="^1.2",
                operations=("snapshot",),
                optional=True,
            ),
        ),
    ),
    setup=setup_runtime_facade,
)

__all__ = ["observe_provider_event", "plugin", "runtime_facade_plugin"]
