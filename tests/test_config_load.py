# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/11 下午11:07
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : test_config_load.py
@Software: PyCharm
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
from liteyuki.config import load_config_in_default


def test_default_load():
    config = load_config_in_default()
    print(json.dumps(config, indent=4, ensure_ascii=False))
