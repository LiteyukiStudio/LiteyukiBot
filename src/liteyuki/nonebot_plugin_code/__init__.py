# python3
# -*- coding: utf-8 -*-
# @Time    : 2021/11/22 14:16
# @Author  : yzyyz
# @Email   :  youzyyz1384@qq.com
# @File    : __init__.py.py
# @Software: PyCh
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, PrivateMessageEvent, GroupMessageEvent, Message
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State
from .run import run
from ..extraApi.badword import *
from ..extraApi.rule import *

runcode = on_command(cmd='code',
                     rule=plugin_enable(pluginId="nb.code") & NOT_BLOCKED & NOT_IGNORED & MODE_DETECT,
                     priority=2, block=True)


@runcode.handle()
async def _(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    try:
        code = str(event.get_message()).strip().replace(r"\\\\", r"\\")
        res = str(await run(code))
        if len(res) >= 2400:
            await runcode.send(message="code:返回字符串过长")
        else:
            if await SUPERUSER(bot, event):
                await runcode.send(message=Message(await badwordFilter(bot, event, state, res)))
            else:
                await runcode.send(message=await badwordFilter(bot, event, state, res))
            if len(res.splitlines()) >= 100 and type(event) is GroupMessageEvent and not await SUPERUSER(bot, event):
                await bot.set_group_ban(group_id=event.group_id, user_id=event.user_id, duration=len(res) * 60)
                await runcode.send(message="code:故意刷屏,禁言与输出文本字符同样多的分钟数:%s分钟" % len(res), at_sender=True)
        line_count = len(event.raw_message.splitlines())
    except BaseException as exception:
        await runcode.send(message="code:出了一些错误, 也有可能是返回字符串太长")
        await runcode.finish(message=exception.__repr__())
