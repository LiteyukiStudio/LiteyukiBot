# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/20 上午5:12
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : liteyuki_reply.py
@Software: PyCharm
"""
from liteyuki.plugin import PluginMetadata, PluginType
from liteyuki.message.on import on_message
from liteyuki.message.event import Event

__plugin_meta__ = PluginMetadata(
    name="你好轻雪",
    type=PluginType.TEST
)


@on_message().handle
async def _(event: Event):
    if str(event.data["raw_message"]) == "你好轻雪":
        event.reply("你好呀")
