# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/22 上午8:39
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : ts_chan_sub.py
@Software: PyCharm
"""
import asyncio

from liteyuki.comm import Channel, get_channel
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import Bot
chan_main = get_channel("chan-main")


# @chan_main.on_receive()
# async def _(data: str):
#     print("Received data from chan-main:", data)
#     try:
#         bot: Bot = get_bot("2443429204")  # type: ignore
#
#         def send_msg():
#
#             bot.send_msg(message_type="private", user_id=2443429204, message=data)
#
#         print("tsA")
#         print("tsA1")
#         await asyncio.ensure_future(c)
#         print("tsB")
#     except Exception as e:
#         print(e)
#         pass
