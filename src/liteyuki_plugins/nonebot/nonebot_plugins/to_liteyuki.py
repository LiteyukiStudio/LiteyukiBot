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
from nonebot.log import logger
from nonebot import on_message, require
from nonebot.adapters import Bot

from liteyuki.session import Session, SceneType

require("nonebot_plugin_uninfo")

from nonebot_plugin_uninfo import get_session, Role, ROLE_LEVEL


__plugin_meta__ = PluginMetadata(
    name="轻雪push",
    description="把消息事件传递给轻雪框架进行处理",
    usage="用户无需使用",
)


ctx = get_ctx()


@on_message(block=False, priority=0).handle()
async def _(bot: Bot, event: MessageEvent):
    session = await get_session(bot, event)
    print("Role", session.member.role)
    new_session = Session(**session.dump())

    logger.debug("SESSION", new_session)
    logger.debug("Pushing message to Liteyuki")
    ctx.sub_chan << event.raw_message
