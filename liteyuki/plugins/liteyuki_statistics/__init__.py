from nonebot.plugin import PluginMetadata
from .stat_matchers import *
from .stat_monitors import *
from .stat_restful_api import *

__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="统计信息",
    description="统计机器人的信息，包括消息、群聊等，支持排名、图表等功能",
    usage=(
            "```\nstatistic message 查看统计消息\n"
            "可选参数:\n"
            "  -g|--group [group_id] 指定群聊\n"
            "  -u|--user [user_id] 指定用户\n"
            "  -d|--duration [duration] 指定时长\n"
            "  -p|--period [period] 指定次数统计周期\n"
            "  -b|--bot [bot_id] 指定机器人\n"
            "命令别名:\n"
            "  statistic|stat  message|msg|m\n"
            "```"
    ),
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki"      : True,
            "toggleable"    : False,
            "default_enable": True,
    }
)
