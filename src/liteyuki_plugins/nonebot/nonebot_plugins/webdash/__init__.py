from nonebot.plugin import PluginMetadata

from .main import *

__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="网页监控面板",
    description="网页监控面板，用于查看机器人的状态和信息",
    usage=(
            "访问 127.0.0.1:port 查看机器人的状态信息\n"
            "stat msg -g|--group [group_id] 查看群的统计信息，不带参数为全群\n"
            "配置项：custom_domain，自定义域名，通常对外用，内网无需"
    ),
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki"      : True,
            "toggleable"    : False,
            "default_enable": True,
    }
)
