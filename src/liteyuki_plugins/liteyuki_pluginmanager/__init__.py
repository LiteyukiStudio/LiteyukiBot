from .manager import *
from .autorun import *
from nonebot import on_message
from .resource import resource
from nonebot.plugin.plugin import plugins, PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="轻雪插件管理",
    description="轻雪内置的插件管理",
    usage="命令：\n"
          "•「help」获取插件列表\n"
          "•「help插件名」获取插件使用方法\n"
          "•「启用/停用xxx」插件开关\n"
          "•「添加插件元数据 name description usage extra」\n",
    extra={
        "force_enable": True,
        "liteyuki_resource": resource,
        "liteyuki_plugin": True
    }
)
