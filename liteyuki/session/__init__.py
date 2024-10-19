# -*- coding: utf-8 -*-
"""
该模块参考并引用了nonebot-plugin-alconna的消息段定义
"""
from typing import Any

from magicoca import Chan, select
from mypy.server.objgraph import Iterable
from six import Iterator


def message_handler_thread(i_chans: Iterable[Chan[Any]]):
    """
    Args:
        i_chans: 多路输入管道组
    Returns:
    """
    for msg in select(*i_chans):
        print("Recv from anybot", msg)