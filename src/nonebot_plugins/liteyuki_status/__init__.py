from nonebot.plugin import PluginMetadata
from .status import *

__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="状态查看器",
    description="",
    usage=(
            "MARKDOWN### 状态查看器\n"
            "查看机器人的状态\n"
            "### 用法\n"
            "- `/status` 查看基本情况\n"
            "- `/status memory` 查看内存使用情况\n"
            "- `/status process` 查看进程情况\n"
    ),
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki": True,
            "toggleable"     : False,
            "default_enable" : True,
    }
)
