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

logger = loguru.logger.bind()

debug_format: str = (
    "<c>{time:YYYY-MM-DD HH:mm:ss}</c> "
    "<lvl>[{level.icon}{level}]</lvl> "
    "<c><{name}.{module}.{function}:{line}></c> "
    "{message}"
)

# 默认日志格式
default_format: str = (
    "<c>{time:MM-DD HH:mm:ss}</c> "
    "<lvl>[{level.icon}{level}]</lvl> "
    "<c><{name}></c> "
    "{message}"
)

def get_format(level: str) -> str:
    """
    获取日志格式
    Args:
        level: 日志等级

    Returns: 日志格式

    """
    # DEBUG日志格式

    if level == "DEBUG":
        return debug_format
    else:
        return default_format


def init_log(config: dict):
    """
    在语言加载完成后执行
    Args:
        config: 配置
    """
    global logger
    level = config.get("log_level", "DEBUG")
    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        diagnose=False,
        format=get_format(level),
    )
    show_icon = config.get("log_icon", True)
    logger.level("DEBUG", color="<blue>", icon=f"{'🐛' if show_icon else ''}")
    logger.level("INFO", color="<normal>", icon=f"{'ℹ️' if show_icon else ''}")
    logger.level("SUCCESS", color="<green>", icon=f"{'✅' if show_icon else ''}")
    logger.level("WARNING", color="<yellow>", icon=f"{'⚠️' if show_icon else ''}")
    logger.level("ERROR", color="<red>", icon=f"{'⭕' if show_icon else ''}")
    logger.level("CRITICAL", color="<red>", icon=f"{'❌' if show_icon else ''}")
    logger.level("TRACE", color="<cyan>", icon=f"{'🔍' if show_icon else ''}")

    logger.bind()

init_log(config={"log_level": "DEBUG", "log_icon": True})