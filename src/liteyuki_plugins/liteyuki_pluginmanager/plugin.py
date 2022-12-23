from typing import Union

from nonebot.adapters.onebot.v11 import PrivateMessageEvent, GroupMessageEvent, Bot
from nonebot.internal.matcher import Matcher
from nonebot.message import event_preprocessor, run_preprocessor
from nonebot.typing import T_State


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
    pass
