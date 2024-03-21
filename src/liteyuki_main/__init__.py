import nonebot
from nonebot.plugin import PluginMetadata
from src.utils.language import get_system_lang
from src.utils.data_manager import *
from .loader import *
from .webdash import *
from src.utils.config import config

__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪主程序",
    description="轻雪主程序插件，包含了许多初始化的功能",
    usage="",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki_plugin": True,
            "toggleable": False,
    }
)

auto_migrate()  # 自动迁移数据库

sys_lang = get_system_lang()
nonebot.logger.info(sys_lang.get("main.current_language", LANG=sys_lang.get("language.name")))
nonebot.logger.info(sys_lang.get("main.enable_webdash", URL=f"http://127.0.0.1:{config.get('port', 8080)}"))
