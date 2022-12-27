from nonebot import require
from .reloader import Reloader


# 可选参数 5秒后触发重启


def restart_bot():
    Reloader.reload()
