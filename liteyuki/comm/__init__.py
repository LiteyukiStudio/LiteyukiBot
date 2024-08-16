# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/7/26 下午10:36
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : __init__.py
@Software: PyCharm
该模块用于轻雪主进程和Nonebot子进程之间的通信
"""
from liteyuki.comm.channel import (
    Channel,
    get_channel,
    set_channel,
    set_channels,
    get_channels,
    active_channel,
    passive_channel
)
from liteyuki.comm.event import Event

__all__ = [
        "Channel",
        "Event",
        "get_channel",
        "set_channel",
        "set_channels",
        "get_channels",
        "active_channel",
        "passive_channel"
]

from liteyuki.utils import IS_MAIN_PROCESS

# 第一次引用必定为赋值
_ref_count = 0
if not IS_MAIN_PROCESS:
    if (active_channel is None or passive_channel is None) and _ref_count > 0:
        raise RuntimeError("Error: Channel not initialized in sub process")
    _ref_count += 1
