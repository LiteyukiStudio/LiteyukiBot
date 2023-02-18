import re
import time
import uuid

from nonebot import get_driver, require
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.exception import IgnoredException
from nonebot.internal.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.utils import run_sync
from nonebot_plugin_apscheduler import scheduler

from ...liteyuki_api.data import *
from ...liteyuki_api.message import *
from ...liteyuki_api.reloader import Reloader
from ...liteyuki_api.update import update_liteyuki, update_resource
from ...liteyuki_api.utils import *

require("nonebot_plugin_apscheduler")

driver = get_driver()





# 通知超级用户Bot连接
@driver.on_bot_connect
async def _(bot: Bot):
    await broad_to_all_superusers(message=(await get_text_by_language("2")).format(BOT_ID=bot.self_id))


# 会话启用预处理
@run_preprocessor
async def _(bot: Bot, matcher: Matcher, event: Union[GroupMessageEvent]):
    white_list = [
    ]
    if matcher.plugin_name not in white_list:
        if await Data(Data.groups, event.group_id).get("enable", True):
            pass
        else:
            if re.search("(#群聊启用)|(#群聊停用)|(#group-enable)|(group-disable)", event.raw_message) and str(event.user_id) in bot.config.superusers:
                pass
            else:
                raise IgnoredException("Session do not enable Bot")
    else:
        # 白名单直接过
        pass


# 屏蔽预处理
@run_preprocessor
async def _(event: MessageEvent):
    banned_user_list = await Data(Data.globals, "liteyuki").get("banned_users", [])
    if event.user_id in banned_user_list:
        raise IgnoredException("User has been blocked")


# execute预处理
@run_preprocessor
async def _():
    pass



