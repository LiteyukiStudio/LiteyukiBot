from nonebot.plugin import PluginMetadata
from .monitors import *
from .matchers import *


__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪智障回复",
    description="",
    usage="",
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
        "liteyuki": True,
        "toggleable"     : True,
        "default_enable" : True,
    }
)