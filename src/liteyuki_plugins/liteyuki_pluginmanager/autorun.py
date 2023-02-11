import traceback

from nonebot import get_driver
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor

from .plugin_api import *

driver = get_driver()

# 插件启用检查
@run_preprocessor
async def _(matcher: Matcher, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    """
    检查插件是否启用，未启用则进行阻断

    :param matcher:
    :param event:
    :return:
    """
    white_list = [
        "liteyuki_pluginmanager"
    ]
    if matcher.plugin_name not in white_list:
        if await check_enabled_stats(event, matcher.plugin_name):
            pass
        else:
            raise IgnoredException
    else:
        pass

# 加载安装的第三方插件
@driver.on_startup
async def _():
    installed_plugin_name_list = await Data(Data.globals, "liteyuki").get("installed_plugin", [])
    if len(installed_plugin_name_list) > 0:
        nonebot.logger.info("Liteyuki is trying to load third-party plugins")
        for plugin_name in installed_plugin_name_list:
            try:
                nonebot.load_plugin(plugin_name)
                nonebot.logger.success(f"Liteyuki load plugin successfully: {plugin_name}")
            except BaseException as e:
                nonebot.logger.warning(f"Liteyuki can not load plugin: {plugin_name}")
    else:
        nonebot.logger.info("No third-party plugin need to load")