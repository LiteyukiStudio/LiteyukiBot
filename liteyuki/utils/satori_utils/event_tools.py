from nonebot.adapters import satori

from liteyuki.utils.base.ly_typing import T_MessageEvent


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
