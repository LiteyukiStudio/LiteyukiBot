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

liteyuki = get_bot()


@liteyuki.on_after_start
def save_startup_timestamp():
    """
    储存启动的时间戳
    """
    startup_timestamp = time.time()
