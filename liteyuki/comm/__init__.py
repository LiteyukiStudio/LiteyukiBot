# -*- coding: utf-8 -*-
"""
该模块用于轻雪主进程和Nonebot子进程之间的通信
依赖关系
event -> _
storage -> channel_
rpc -> channel_, storage
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
