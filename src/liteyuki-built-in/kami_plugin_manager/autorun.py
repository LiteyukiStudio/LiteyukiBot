import os.path
from nonebot.exception import IgnoredException
from nonebot.message import run_preprocessor
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.matcher import Matcher
from nonebot.typing import T_State
from typing import Union
from ...extraApi.rule import check_plugin_enable


@run_preprocessor
async def check(matcher: Matcher, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    if await check_plugin_enable(matcher.plugin_name)(bot, event, state):
        pass
    else:
        if matcher.plugin_name in ["kami_plugin_manager", "kami_base", "kami_user_manager", "kami_super_tool"]:
            pass
        else:
            raise IgnoredException("插件未启用")
