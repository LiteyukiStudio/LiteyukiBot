from .manager import *
from .autorun import *
from nonebot import on_message
from nonebot.plugin.plugin import plugins, PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="轻雪插件管理",
    description="轻雪内置的插件管理",
    usage="无",
    extra={
        "force_enable": True
    }
)
