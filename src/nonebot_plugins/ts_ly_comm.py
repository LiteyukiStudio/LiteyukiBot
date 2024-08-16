# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/16 下午8:30
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : ts_ly_comm.py
@Software: PyCharm
"""
from nonebot.plugin import PluginMetadata
from liteyuki.comm.storage import shared_memory

__plugin_meta__ = PluginMetadata(
    name="轻雪通信测试",
    description="用于测试轻雪插件通信",
    usage="不面向用户",
)

print("共享内存数据：", shared_memory.get("startup_timestamp", default=None))