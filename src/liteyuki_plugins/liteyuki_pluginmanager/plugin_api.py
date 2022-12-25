from typing import Union

import poetry_plugin_export.walker

from ...liteyuki_api.data import Data
from nonebot.plugin import Plugin
from nonebot.plugin.plugin import plugins
from nonebot.plugin import get_loaded_plugins
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, MessageSegment


def search_for_plugin(keyword: str) -> Union[Plugin, None]:
    """
    模糊搜索插件

    :param keyword: 搜索关键词
    :return:
    """
    # 精准搜搜
    for p in get_loaded_plugins():
        if p.metadata is not None:
            if keyword == p.metadata.name:
                return p
        else:
            if keyword == p.name:
                return p

    # 模糊搜索
    for p in get_loaded_plugins():
        if p.metadata is not None:
            if keyword in p.metadata.name or p.metadata.name in keyword:
                return p
        else:
            if keyword in p.name or p.name in keyword:
                return p

    return None


def get_plugin(plugin_name) -> Plugin:
    """
    通过插件名获取插件

    :param plugin_name:
    :return:
    """
    return plugins[plugin_name]


def get_plugin_default_stats(plugin_name) -> bool:
    plugin = get_plugin(plugin_name)
    if plugin.metadata is not None:
        default_enable = plugin.metadata.extra.get("default_enable", True)
    else:
        default_enable = True
    return default_enable


def check_enabled_stats(event: Union[GroupMessageEvent, PrivateMessageEvent], plugin_name) -> bool:
    """
    检查返回插件是否启用

    :param event: 会话
    :param plugin_name:
    :return:
    """
    db = Data(*Data.get_type_id(event))
    enabled_plugin = db.get_data("enabled_plugin", [])
    disabled_plugin = db.get_data("disabled_plugin", [])
    default_enable = get_plugin_default_stats(plugin_name)
    if default_enable and plugin_name not in disabled_plugin or not default_enable and plugin_name in enabled_plugin:
        return True
    else:
        return False


def generate_plugin_image() -> MessageSegment.image:
    pass
