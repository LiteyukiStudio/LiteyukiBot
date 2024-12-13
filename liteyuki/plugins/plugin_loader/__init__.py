# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/11 下午10:02
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : __init__.py.py
@Software: PyCharm
"""
from liteyuki import get_config, load_plugin
from liteyuki.plugin import PluginMetadata, load_plugins, PluginType

__plugin_meta__ = PluginMetadata(
    name="外部轻雪插件加载器",
    description="插件加载器，用于加载轻雪原生插件",
    type=PluginType.SERVICE
)


def default_plugins_loader():
    """
    默认插件加载器，应在初始化时调用
    """
    for plugin in get_config("liteyuki.plugins", []):
        load_plugin(plugin)

    for plugin_dir in get_config("liteyuki.plugin_dirs", ["src/liteyuki_plugins"]):
        load_plugins(plugin_dir)


default_plugins_loader()
