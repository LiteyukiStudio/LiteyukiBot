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

from nonebot import Bot, get_bot, on_message, get_driver
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent, Bot

from liteyuki import Channel
from liteyuki.comm import get_channel
from liteyuki.comm.storage import shared_memory
from liteyuki.session.event import MessageEvent as LiteyukiMessageEvent

__plugin_meta__ = PluginMetadata(
    name="轻雪push",
    description="把消息事件传递给轻雪框架进行处理",
    usage="用户无需使用",
)

recv_channel = Channel[LiteyukiMessageEvent](name="event_to_nonebot")


# @on_message().handle()
# async def _(bot: Bot, event: MessageEvent):
#     liteyuki_event = LiteyukiMessageEvent(
#         message_type=event.message_type,
#         message=event.dict()["message"],
#         raw_message=event.raw_message,
#         data=event.dict(),
#         bot_id=bot.self_id,
#         user_id=str(event.user_id),
#         session_id=str(event.user_id if event.message_type == "private" else event.group_id),
#         session_type=event.message_type,
#         receive_channel=recv_channel,
#     )
#     shared_memory.publish("event_to_liteyuki", liteyuki_event)


# @get_driver().on_bot_connect
# async def _():
#     while True:
#         event = await recv_channel.async_receive()
#         bot: Bot = get_bot(event.bot_id)  # type: ignore
#         if event.message_type == "private":
#             await bot.send_private_msg(user_id=int(event.session_id), message=event.data["message"])
#         elif event.message_type == "group":
#             await bot.send_group_msg(group_id=int(event.session_id), message=event.data["message"])
