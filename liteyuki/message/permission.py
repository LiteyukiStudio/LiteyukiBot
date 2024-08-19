# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/19 下午10:55
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : permission.py
@Software: PyCharm
"""

from typing import Callable, Coroutine, TypeAlias

PERMISSION_HANDLER: TypeAlias = Callable[[str], bool | Coroutine[None, None, bool]]


class Permission:
    def __init__(self, handler: PERMISSION_HANDLER):
        self.handler = handler

