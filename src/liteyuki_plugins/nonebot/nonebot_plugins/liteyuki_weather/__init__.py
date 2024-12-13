from nonebot.plugin import PluginMetadata
from nonebot import get_driver
from .qweather import *

__plugin_meta__ = PluginMetadata(
    name="轻雪天气",
    description="基于和风天气api的天气插件",
    usage="",
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki"      : True,
            "toggleable"    : True,
            "default_enable": True,
    }
)

from src.utils.base.data_manager import set_memory_data

driver = get_driver()


@driver.on_startup
async def _():
    # 检查是否为开发者模式
    is_dev = await check_key_dev(get_config("weather_key", ""))
    set_memory_data("weather.is_dev", is_dev)
