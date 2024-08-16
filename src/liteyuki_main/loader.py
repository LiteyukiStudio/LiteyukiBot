import asyncio

import nonebot.plugin
from nonebot import get_driver
from src.utils import init_log
from src.utils.base.config import get_config
from src.utils.base.data_manager import InstalledPlugin, plugin_db
from src.utils.base.resource import load_resources
from src.utils.message.tools import check_for_package

from liteyuki import get_bot

from nonebot_plugin_apscheduler import scheduler

load_resources()
init_log()

driver = get_driver()


@driver.on_startup
async def load_plugins():
    nonebot.plugin.load_plugins("src/nonebot_plugins")
    # 从数据库读取已安装的插件
    if not get_config("safe_mode", False):
        # 安全模式下，不加载插件
        installed_plugins: list[InstalledPlugin] = plugin_db.where_all(InstalledPlugin())
        if installed_plugins:
            for installed_plugin in installed_plugins:
                if not check_for_package(installed_plugin.module_name):
                    nonebot.logger.error(
                        f"{installed_plugin.module_name} not installed, but in loading database. please run `npm fixup` in chat to reinstall it.")
                else:
                    nonebot.load_plugin(installed_plugin.module_name)
        nonebot.plugin.load_plugins("plugins")
    else:
        nonebot.logger.info("Safe mode is on, no plugin loaded.")
