# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/20 上午5:10
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : to_liteyuki.py
@Software: PyCharm
"""
import asyncio

from nonebot import Bot, get_bot, on_message
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent, Bot
from liteyuki.comm.storage import shared_memory
from liteyuki.message.event import MessageEvent as LiteyukiMessageEvent

__plugin_meta__ = PluginMetadata(
    name="轻雪物流",
    description="把消息事件传递给轻雪框架进行处理",
    usage="用户无需使用",
)


@on_message().handle()
async def _(bot: Bot, event: MessageEvent):
    liteyuki_event = LiteyukiMessageEvent(
        message_type=event.message_type,
        message=event.dict()["message"],
        raw_message=event.raw_message,
        data=event.dict(),
        bot_id=bot.self_id,
        session_id=str(event.user_id if event.message_type == "private" else event.group_id),
        session_type=event.message_type,
        receive_channel="event_to_nonebot"
    )
    shared_memory.publish("event_to_liteyuki", liteyuki_event)


@shared_memory.on_subscriber_receive("event_to_nonebot")
async def _(event: LiteyukiMessageEvent):
    bot: Bot = get_bot(event.bot_id)
    if event.message_type == "private":
        await bot.send_private_msg(user_id=int(event.session_id), message=event.data["message"])
    elif event.message_type == "group":
        await bot.send_group_msg(group_id=int(event.session_id), message=event.data["message"])
