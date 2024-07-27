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
from typing import TYPE_CHECKING

logger = loguru.logger
if TYPE_CHECKING:
    # avoid sphinx autodoc resolve annotation failed
    # because loguru module do not have `Logger` class actually
    from loguru import Record


def default_filter(record: "Record"):
    """默认的日志过滤器，根据 `config.log_level` 配置改变日志等级。"""
    log_level = record["extra"].get("nonebot_log_level", "INFO")
    levelno = logger.level(log_level).no if isinstance(log_level, str) else log_level
    return record["level"].no >= levelno


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


logger = loguru.logger.bind()


def init_log(config: dict):
    """
    在语言加载完成后执行
    Returns:

    """
    global logger

    logger.remove()
    logger.add(
        sys.stdout,
        level=0,
        diagnose=False,
        filter=default_filter,
        format=get_format(config.get("log_level", "INFO")),
    )
    show_icon = config.get("log_icon", True)

    # debug = lang.get("log.debug", default="==DEBUG")
    # info = lang.get("log.info", default="===INFO")
    # success = lang.get("log.success", default="SUCCESS")
    # warning = lang.get("log.warning", default="WARNING")
    # error = lang.get("log.error", default="==ERROR")
    #
    # logger.level("DEBUG", color="<blue>", icon=f"{'🐛' if show_icon else ''}{debug}")
    # logger.level("INFO", color="<normal>", icon=f"{'ℹ️' if show_icon else ''}{info}")
    # logger.level("SUCCESS", color="<green>", icon=f"{'✅' if show_icon else ''}{success}")
    # logger.level("WARNING", color="<yellow>", icon=f"{'⚠️' if show_icon else ''}{warning}")
    # logger.level("ERROR", color="<red>", icon=f"{'⭕' if show_icon else ''}{error}")
