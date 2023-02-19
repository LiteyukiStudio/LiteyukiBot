import os
import time
import uuid

import nonebot
from nonebot import on_keyword, require, get_driver
from nonebot.utils import run_sync
from nonebot_plugin_apscheduler import scheduler

from ...liteyuki_api.config import Path
from ...liteyuki_api.data import Data
from ...liteyuki_api.message import broad_to_all_superusers
from ...liteyuki_api.reloader import Reloader
from ...liteyuki_api.update import update_resource, update_liteyuki
from ...liteyuki_api.utils import get_local_version, get_depository_version, get_text_by_language

require("nonebot_plugin_apscheduler")

driver = get_driver()


# 资源初始化
@driver.on_startup
async def _():
    await Data(Data.globals, "liteyuki").set("start_time", list(time.localtime())[0:6])
    # 没有就克隆
    if not os.path.exists(os.path.join(Path.res, ".git")) or not os.path.exists(os.path.join(Path.res, "version.json")):
        await run_sync(os.system)(f"git clone https://gitee.com/snowykami/liteyuki-resource {os.path.join(Path.res)}")


# 自动更新
@scheduler.scheduled_job("cron", hour=4, minute=0, second=0)
async def auto_update():
    nonebot.logger.info("Start to check for update")
    local_version_name, local_version_id, local_resource_id = get_local_version()
    online_version_name, online_version_id, online_resource_id = get_depository_version()
    reload = False
    if online_resource_id > local_resource_id:
        # 更新资源
        nonebot.logger.info(f"Updating resource: {local_version_name}.{local_resource_id} -> {online_version_name}.{online_resource_id}")
        await run_sync(update_resource)()
        reload = True
    if online_version_id > local_version_id:
        # 更新版本和资源
        nonebot.logger.info(f"Updating Liteyuki: {local_version_name}.{local_version_id} -> {online_version_name}.{online_version_id}")
        await run_sync(update_liteyuki)()
        await run_sync(update_resource)()
        reload = True
    if reload:
        # 只要有更新就Reload
        nonebot.logger.success(await get_text_by_language("10000009"))
        await broad_to_all_superusers(await get_text_by_language("10000009"))
        Reloader().reload()
