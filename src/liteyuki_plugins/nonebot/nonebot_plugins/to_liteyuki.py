# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/20 上午5:10
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : to_liteyuki.py
@Software: PyCharm
"""

from croterline.process import get_ctx
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot import on_message

__plugin_meta__ = PluginMetadata(
    name="轻雪push",
    description="把消息事件传递给轻雪框架进行处理",
    usage="用户无需使用",
)

ctx = get_ctx()

@on_message().handle()
async def _(event: MessageEvent):
    print("Push message to Liteyuki")

    ctx.sub_chan << event.raw_message

