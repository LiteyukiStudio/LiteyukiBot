# -*- coding: utf-8 -*-
"""
本模块用于轻雪主进程和子进程之间的通信的事件类
"""
from typing import Any


class Event:
    """
    事件类
    """

    def __init__(self, name: str, data: dict[str, Any]):
        self.name = name
        self.data = data
