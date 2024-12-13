from nonebot.plugin import PluginMetadata
from .npm import *
from .rpm import *

__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪包管理器v2",
    description="npm & rpm",
    usage=(
            "npm list\n"
            "npm enable/disable <plugin_name>\n"
            "npm search <keywords...>\n"
            "npm install/uninstall <plugin_name>\n"
    ),
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki"      : True,
            "toggleable"    : False,
            "always_on"     : True,
            "default_enable": False,
    }
)
