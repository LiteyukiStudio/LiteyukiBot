from typing import Union

from nonebot.adapters.onebot.v11 import PrivateMessageEvent, GroupMessageEvent, Bot
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.typing import T_State
from .plugin_api import *

from ...liteyuki_api.data import Data


@run_preprocessor
async def _(matcher: Matcher, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    """
    检查插件是否启用，未启用则进行阻断

    :param matcher:
    :param bot:
    :param event:
    :param state:
    :return:
    """
    white_list = [
        "liteyuki_pluginmanager"
    ]
    if matcher.plugin_name not in white_list:
        if check_enabled_stats(event, matcher.plugin_name):
            pass
        else:
            raise IgnoredException
    else:
        pass
