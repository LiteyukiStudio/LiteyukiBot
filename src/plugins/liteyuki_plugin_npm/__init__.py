from nonebot.plugin import PluginMetadata
from .manager import *
from .installer import *
from .helper import *

__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪插件管理",
    description="本地插件管理和插件商店支持，支持启用/停用，安装/卸载插件",
    usage=(
            "lnpm list\n"
            "lnpm enable/disable <plugin_name>\n"
            "lnpm search <keywords...>\n"
            "lnpm install/uninstall <plugin_name>\n"
    ),
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki_plugin": True,
    }
)
