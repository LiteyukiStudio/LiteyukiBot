# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/19 下午10:30
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : __init__.py.py
@Software: PyCharm
"""
from nonebot import require

from liteyuki.comm.storage import shared_memory

require("nonebot_plugin_alconna")

from nonebot_plugin_alconna import UniMessage, Command, on_alconna

