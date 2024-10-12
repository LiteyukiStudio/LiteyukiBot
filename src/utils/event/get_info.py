from nonebot.adapters import satori
from nonebot.adapters import onebot
from src.utils.base.ly_typing import T_MessageEvent, T_GroupMessageEvent


def get_user_id(event: T_MessageEvent):
    if isinstance(event, satori.event.Event):
        return event.user.id
    else:
        return event.user_id


def get_group_id(event: T_GroupMessageEvent):
    if isinstance(event, satori.event.Event):
        return event.guild.id
    elif isinstance(event, onebot.v11.GroupMessageEvent):
        return event.group_id
    else:
        return None


def get_message_type(event: T_MessageEvent) -> str:
    if isinstance(event, satori.event.Event):
        return "private" if event.guild is None else "group"
    else:
        return event.message_type
