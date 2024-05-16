from nonebot.adapters import satori

from liteyuki.utils.base.ly_typing import T_MessageEvent


def get_message_type(event: T_MessageEvent) -> str:
    if isinstance(event, satori.event.Event):
        return "private" if event.guild is None else "group"
    else:
        return event.message_type
