# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/19 下午8:57
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : ts_sm.py
@Software: PyCharm
"""
import asyncio

from liteyuki.comm.storage import shared_memory
from liteyuki import get_bot


@shared_memory.on_subscriber_receive("to_liteyuki")
async def _(data):
    print("主进程接收数据async：", data)
