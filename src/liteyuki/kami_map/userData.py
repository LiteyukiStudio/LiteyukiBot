from typing import Union

from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot
from nonebot import on_command
from nonebot.typing import T_State

from extraApi.base import Session
from extraApi.rule import pluginEnable

bind_home = on_command(cmd="设置家庭地址", rule=pluginEnable("kami.map"), priority=10, block=True)


@bind_home.handle()
async def bind_home_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    try:
        pass
    except BaseException as e:
        await Session.sendException(bot, event, state, e)
