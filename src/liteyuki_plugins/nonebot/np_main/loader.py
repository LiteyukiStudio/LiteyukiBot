import asyncio
import os.path
from pathlib import Path

import nonebot.plugin
from nonebot import get_driver
from src.utils import init_log
from src.utils.base.config import get_config
from src.utils.base.data_manager import InstalledPlugin, plugin_db
from src.utils.base.resource import load_resources
from src.utils.message.tools import check_for_package

load_resources()
init_log()

driver = get_driver()


@driver.on_startup
async def load_plugins():
    nonebot.plugin.load_plugins(os.path.abspath(os.path.join(os.path.dirname(__file__), "../nonebot_plugins")))
    # 从数据库读取已安装的插件
    if not get_config("safe_mode", False):
        # 安全模式下，不加载插件
        installed_plugins: list[InstalledPlugin] = plugin_db.where_all(
            InstalledPlugin()
        )
        if installed_plugins:
            for installed_plugin in installed_plugins:
                if not check_for_package(installed_plugin.module_name):
                    nonebot.logger.error(
                        f"{installed_plugin.module_name} not installed, but still in loader index."
                    )
                else:
                    nonebot.load_plugin(installed_plugin.module_name)
        nonebot.plugin.load_plugins("plugins")
    else:
        nonebot.logger.info("Safe mode is on, no plugin loaded.")
