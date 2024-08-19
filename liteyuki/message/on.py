# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/19 下午10:52
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : on.py
@Software: PyCharm
"""

from liteyuki.message.matcher import Matcher

_matcher_list: list[Matcher] = []


def on_message(permission) -> Matcher:
    pass
