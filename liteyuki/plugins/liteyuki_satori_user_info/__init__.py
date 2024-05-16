from nonebot.plugin import PluginMetadata
from .auto_update import *

__author__ = "expliyh"
__plugin_meta__ = PluginMetadata(
    name="Satori 用户数据自动更新(临时措施)",
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
