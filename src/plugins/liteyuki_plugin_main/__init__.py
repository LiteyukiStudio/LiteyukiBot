import nonebot
from nonebot.plugin import PluginMetadata
from src.utils.language import get_system_lang
from .loader import *
from .webdash import *

__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪主程序",
    description="轻雪主程序插件，包含了许多初始化的功能",
    usage="",
    homepage="https://github.com/snowykami/LiteyukiBot",
)

from src.utils.config import config

sys_lang = get_system_lang()
nonebot.logger.info(sys_lang.get("main.current_language", LANG=sys_lang.get("language.name")))
nonebot.logger.info(sys_lang.get("main.enable_webdash", URL=f"http://{config['nonebot']['host']}:{config['nonebot']['port']}"))
