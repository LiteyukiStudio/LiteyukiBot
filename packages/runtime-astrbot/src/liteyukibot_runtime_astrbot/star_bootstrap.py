"""Source installed into an AstrBot workspace as the Liteyuki ingress Star plugin."""

# mypy: ignore-errors

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import EventMessageType

from liteyukibot_runtime_astrbot.listener import forward_native_event


class LiteyukiBrokerIngressPlugin(star.Star):
    """Observe every native message while leaving AstrBot's local pipeline intact."""

    @filter.event_message_type(EventMessageType.ALL)
    async def forward(self, event: AstrMessageEvent) -> None:
        await forward_native_event(event)
