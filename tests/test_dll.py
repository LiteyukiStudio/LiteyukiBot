# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/7 下午11:44
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : test_dll.py
@Software: PyCharm
"""
from src.utils.extension import load_lib


a = load_lib("src/libs/ly_api")

a.Register("sss", "sss", 64, "sss", "sss")