from nonebot import require

require("nonebot_plugin_reboot")
from .nonebot_plugin_reboot import Reloader

 # 可选参数 5秒后触发重启


def restart_bot():
    Reloader.reload()
