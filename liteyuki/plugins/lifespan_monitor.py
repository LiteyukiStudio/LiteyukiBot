# -*- coding: utf-8 -*-
#
# Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 
#
# @Time    : 2024/7/22 上午11:25
# @Author  : snowykami
# @Email   : snowykami@outlook.com
# @File    : asa.py
# @Software: PyCharm
from liteyuki.plugin import PluginMetadata
from liteyuki import get_bot, logger

__plugin_meta__ = PluginMetadata(
    name="lifespan_monitor",
)

bot = get_bot()


@bot.on_before_start
def _():
    logger.info("生命周期监控器：准备启动")


@bot.on_before_shutdown
def _():
    logger.info("生命周期监控器：准备停止")


@bot.on_before_restart
def _():
    logger.info("生命周期监控器：准备重启")


@bot.on_after_start
def _():
    logger.info("生命周期监控器：启动完成")
