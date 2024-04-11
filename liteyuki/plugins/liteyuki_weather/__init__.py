from nonebot.plugin import PluginMetadata
from .qweather import *


__plugin_meta__ = PluginMetadata(
    name="轻雪天气",
    description="基于和风天气api的天气插件",
    usage="",
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki": True,
            "toggleable"     : True,
            "default_enable" : True,
    }
)

