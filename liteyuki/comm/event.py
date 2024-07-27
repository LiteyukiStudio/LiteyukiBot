# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/7/26 下午10:47
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : event.py
@Software: PyCharm
"""
from typing import Any


class Event:
    """
    事件类
    """

    def __init__(self, name: str, data: dict[str, Any]):
        self.name = name
        self.data = data
