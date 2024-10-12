from nonebot.plugin import PluginMetadata

from .core import *
from .loader import *
__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪核心插件",
    description="轻雪主程序插件，包含了许多初始化的功能",
    usage="",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki"  : True,
            "toggleable": False,
    }
)

from src.utils.base.language import Language, get_default_lang_code

sys_lang = Language(get_default_lang_code())
nonebot.logger.info(sys_lang.get("main.current_language", LANG=sys_lang.get("language.name")))