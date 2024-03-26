from nonebot.plugin import PluginMetadata

from .profile_manager import *

__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪用户管理",
    description="用户管理插件",
    usage="",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki"      : True,
            "toggleable"    : False,
            "default_enable": True,
    }
)
