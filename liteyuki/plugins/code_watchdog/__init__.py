# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/11 下午8:50
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : __init__.py.py
@Software: PyCharm
"""
from liteyuki.core import IS_MAIN_PROCESS
from liteyuki.plugin import PluginMetadata

from .observer import *

__plugin_meta__ = PluginMetadata(
    name="代码热重载监视",
)

if IS_MAIN_PROCESS:
    config = get_config("liteyuki.reload")
