# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/19 下午10:47
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : event.py
@Software: PyCharm
"""


class Event:
    def __init__(self, type_: str, data: dict):
        self.type = type_
        self.data = data
