# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/11 下午5:24
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : __init__.py.py
@Software: PyCharm
"""

import nonebot

from liteyuki.plugin import PluginMetadata
from liteyuki import get_bot
from liteyuki.comm import Channel, set_channel
from liteyuki.core import IS_MAIN_PROCESS
from .nb_utils import adapter_manager, driver_manager

__plugin_meta__ = PluginMetadata(
    name="NoneBot2启动器",
)

liteyuki = get_bot()


def nb_run(chan_active: "Channel", chan_passive: "Channel", **kwargs):
    """
    初始化NoneBot并运行在子进程
    Args:

        chan_active:
        chan_passive:
        **kwargs:

    Returns:
    """
    # 给子进程传递通道对象
    set_channel("nonebot-active", chan_active)
    set_channel("nonebot-passive", chan_passive)

    kwargs.update(kwargs.get("nonebot", {}))    # nonebot配置优先
    nonebot.init(**kwargs)

    driver_manager.init(config=kwargs)
    adapter_manager.init(kwargs)
    adapter_manager.register()
    nonebot.load_plugin("src.liteyuki_main")
    nonebot.run()


if IS_MAIN_PROCESS:
    @liteyuki.on_after_start
    def start_run_nonebot():
        liteyuki.process_manager.add_target(name="nonebot", target=nb_run, args=(), kwargs=liteyuki.config)
        liteyuki.process_manager.start("nonebot")
