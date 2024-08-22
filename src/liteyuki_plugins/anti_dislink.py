# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/22 上午9:06
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : anti_dislink.py
@Software: PyCharm
"""
import random
from liteyuki.plugin import PluginMetadata, PluginType

from liteyuki.message.on import on_keywords

__plugin_meta__ = PluginMetadata(
    name="严禁断联化",
    type=PluginType.APPLICATION
)


@on_keywords(["看看你的", "看看j", "给我看看"]).handle()
async def _(event):
    event.reply(random.choice(["No dislink", "严禁断联化"]))
