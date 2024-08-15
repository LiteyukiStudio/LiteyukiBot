# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/15 下午11:29
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : __init__.py.py
@Software: PyCharm
"""
from liteyuki.plugin import PluginMetadata

from .divided_by_lifespan import *

__plugin_mata__ = PluginMetadata(
    name="计划任务",
    description="计划任务插件，一些杂项任务的计划执行。",
)
