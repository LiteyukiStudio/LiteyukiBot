from nonebot.plugin import PluginMetadata
from .minesweeper import *

__plugin_meta__ = PluginMetadata(
    name="轻雪小游戏",
    description="内置了一些小游戏",
    usage="",
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki": True,
            "toggleable"     : True,
            "default_enable" : True,
    }
)
