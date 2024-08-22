# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/22 上午8:37
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : ts_chan_main.py
@Software: PyCharm
"""
import asyncio

from liteyuki.comm import Channel, set_channel, get_channel
from liteyuki import get_bot

set_channel("chan-main", Channel("chan-main"))
set_channel("chan-sub", Channel("chan-sub"))

chan_main = get_channel("chan-main")


# @get_bot().on_after_start
# async def _():
#     while True:
#         chan_main.send("Hello, World!")
#         await asyncio.sleep(5)
