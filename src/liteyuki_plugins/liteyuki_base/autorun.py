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


# 保存启动时间和下载资源
@driver.on_startup
async def _():
    await Data(Data.globals, "liteyuki").set("start_time", list(time.localtime())[0:6])
    if await Data(Data.globals, "liteyuki").get("liteyuki_id") is None:
        await Data(Data.globals, "liteyuki").set("liteyuki_id", str(uuid.uuid4()))

    # 没有就克隆
    if not os.path.exists(os.path.join(Path.res, ".git")) or not os.path.exists(os.path.join(Path.res, "version.json")):
        await run_sync(os.system)(f"git clone https://gitee.com/snowykami/liteyuki-resource src/resource")


# 通知用户Bot连接
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
            if re.search("(#群聊启用)|(#群聊停用)|(#group-enable)|(group-disable)") and str(event.user_id) in bot.config.superusers:
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

# 自动更新
@scheduler.scheduled_job("cron", hour=4, minute=0, second=0)
async def auto_update():
    nonebot.logger.info("Start to check for update")
    local_version_name, local_version_id, local_resource_id = get_local_version()
    online_version_name, online_version_id, online_resource_id = get_depository_version()
    reload = False
    if online_resource_id > local_resource_id:
        nonebot.logger.info(f"Updating resource: {local_version_name}.{local_resource_id} -> {online_version_name}.{online_resource_id}")
        await run_sync(update_resource)()
        reload = True
    if online_version_id > local_version_id:
        nonebot.logger.info(f"Updating Liteyuki: {local_version_name}.{local_version_id} -> {online_version_name}.{online_version_id}")
        await run_sync(update_liteyuki)()
        await run_sync(update_resource)()
        reload = True

    if reload:
        nonebot.logger.success(await get_text_by_language("10000009"))
        await broad_to_all_superusers(await get_text_by_language("10000009"))
        Reloader().reload()

