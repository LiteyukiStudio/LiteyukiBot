# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/11 下午8:22
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : reloader.py.py
@Software: PyCharm
"""
from liteyuki.plugin import PluginMetadata, PluginType

__plugin_meta__ = PluginMetadata(
    name="重启",
    author="snowykami",
    description="进程管理器，用于管理子进程",
    type=PluginType.MODULE
)
