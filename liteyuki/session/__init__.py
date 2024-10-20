# -*- coding: utf-8 -*-
"""
该模块参考并引用了nonebot-plugin-alconna的消息段定义
"""
from typing import Any
from typing import Iterable

from magicoca import Chan, select

from liteyuki.log import logger


def message_handler_thread(i_chans: Iterable[Chan[Any]]):
    """
    Args:
        i_chans: 多路输入管道组
    Returns:
    """
    for msg in select(*i_chans):
        logger.debug(f"Recv from anybot {msg}")
        logger.info(f"Recv from anybot {msg}")