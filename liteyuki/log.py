# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/7/27 上午9:12
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : log.py
@Software: PyCharm
"""
import sys

import loguru

logger = loguru.logger

# DEBUG日志格式
debug_format: str = (
        "<c>{time:YYYY-MM-DD HH:mm:ss}</c> "
        "<lvl>[{level.icon}]</lvl> "
        "<c><{name}.{module}.{function}:{line}></c> "
        "{message}"
)

# 默认日志格式
default_format: str = (
        "<c>{time:MM-DD HH:mm:ss}</c> "
        "<lvl>[{level.icon}]</lvl> "
        "<c><{name}></c> "
        "{message}"
)


def get_format(level: str) -> str:
    if level == "DEBUG":
        return debug_format
    else:
        return default_format


def init_log(config: dict):
    """
    在语言加载完成后执行
    Returns:

    """

    logger.remove()
    logger.add(
        sys.stdout,
        level=0,
        diagnose=False,
        format=get_format(config.get("log_level", "INFO")),
    )
    show_icon = config.get("log_icon", True)
    logger.level("DEBUG", color="<blue>", icon=f"{'🐛' if show_icon else ''}DEBUG")
    logger.level("INFO", color="<normal>", icon=f"{'ℹ️' if show_icon else ''}INFO")
    logger.level("SUCCESS", color="<green>", icon=f"{'✅' if show_icon else ''}SUCCESS")
    logger.level("WARNING", color="<yellow>", icon=f"{'⚠️' if show_icon else ''}WARNING")
    logger.level("ERROR", color="<red>", icon=f"{'⭕' if show_icon else ''}ERROR")


init_log(config={})
