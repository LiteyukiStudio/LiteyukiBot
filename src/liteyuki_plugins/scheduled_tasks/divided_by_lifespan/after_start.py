# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/15 下午11:32
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : after_start.py
@Software: PyCharm
"""
import time

from liteyuki import get_bot
from liteyuki.comm.storage import shared_memory

liteyuki = get_bot()


@liteyuki.on_before_start
def save_startup_timestamp():
    """
    储存启动的时间戳
    """
    startup_timestamp = time.time()
    shared_memory.set("startup_timestamp", startup_timestamp)
