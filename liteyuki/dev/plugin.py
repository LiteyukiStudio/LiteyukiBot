# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/18 上午5:04
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : plugin.py
@Software: PyCharm
"""
from pathlib import Path

from liteyuki.bot import LiteyukiBot
from liteyuki.config import load_config_in_default


def run_plugins(*module_path: str | Path):
    """
    运行插件，无需手动初始化bot
    Args:
        module_path: 插件路径，参考`liteyuki.load_plugin`的函数签名
    """
    cfg = load_config_in_default()
    plugins = cfg.get("liteyuki.plugins", [])
    plugins.extend(module_path)
    cfg["liteyuki.plugins"] = plugins
    bot = LiteyukiBot(**cfg)
    bot.run()
