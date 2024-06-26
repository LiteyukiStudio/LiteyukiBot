from nonebot.adapters import satori

from src.utils.base.ly_typing import T_MessageEvent


def get_user_id(event: T_MessageEvent):
    if isinstance(event, satori.event.Event):
        return event.user.id
    else:
        return event.user_id


def get_group_id(event: T_MessageEvent):
    if isinstance(event, satori.event.Event):
        return event.guild.id
    else:
        return event.group_id


def get_message_type(event: T_MessageEvent) -> str:
    if isinstance(event, satori.event.Event):
        return "private" if event.guild is None else "group"
    else:
        return event.message_type
