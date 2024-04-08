import json
from typing import Optional

import aiofiles
import nonebot.plugin

from liteyuki.utils.data import LiteModel
from liteyuki.utils.data_manager import GlobalPlugin, Group, User, group_db, plugin_db, user_db
from liteyuki.utils.ly_typing import T_MessageEvent


class PluginTag(LiteModel):
    label: str
    color: str = '#000000'


class StorePlugin(LiteModel):
    name: str
    desc: str
    module_name: str  # 插件商店中的模块名不等于本地的模块名，前者是文件夹名，后者是点分割模块名
    project_link: str = ""
    homepage: str = ""
    author: str = ""
    type: str | None = None
    version: str | None = ""
    time: str = ""
    tags: list[PluginTag] = []
    is_official: bool = False


def get_plugin_exist(plugin_name: str) -> bool:
    """
    获取插件是否存在
    Args:
        plugin_name:

    Returns:

    """
    for plugin in nonebot.plugin.get_loaded_plugins():
        if plugin.name == plugin_name:
            return True
    return False


async def get_store_plugin(plugin_name: str) -> Optional[StorePlugin]:
    """
    获取插件信息

    Args:
        plugin_name (str): 插件模块名

    Returns:
        Optional[StorePlugin]: 插件信息
    """
    async with aiofiles.open("data/liteyuki/plugins.json", "r", encoding="utf-8") as f:
        plugins: list[StorePlugin] = [StorePlugin(**pobj) for pobj in json.loads(await f.read())]
    for plugin in plugins:
        if plugin.name == plugin_name:
            return plugin
    return None


def get_plugin_default_enable(plugin_name: str) -> bool:
    """
    获取插件默认启用状态，由插件定义，不存在则默认为启用

    Args:
        plugin_name (str): 插件模块名

    Returns:
        bool: 插件默认状态
    """
    plug = nonebot.plugin.get_plugin(plugin_name)
    return (plug.metadata.extra.get("default_enable", True)
            if plug.metadata else True) if plug else True


def get_plugin_session_enable(event: T_MessageEvent, plugin_name: str) -> bool:
    """
    获取插件当前会话启用状态

    Args:
        event: 会话事件
        plugin_name (str): 插件模块名

    Returns:
        bool: 插件当前状态
    """
    if event.message_type == "group":
        session: Group = group_db.first(Group(), "group_id = ?", event.group_id, default=Group(group_id=str(event.group_id)))
    else:
        session: User = user_db.first(User(), "user_id = ?", event.user_id, default=User(user_id=str(event.user_id)))
    # 默认停用插件在启用列表内表示启用
    # 默认停用插件不在启用列表内表示停用
    # 默认启用插件在停用列表内表示停用
    # 默认启用插件不在停用列表内表示启用
    default_enable = get_plugin_default_enable(plugin_name)
    if default_enable:
        return plugin_name not in session.disabled_plugins
    else:
        return plugin_name in session.enabled_plugins


def get_plugin_global_enable(plugin_name: str) -> bool:
    nonebot.plugin.get_plugin(plugin_name)
    return plugin_db.first(
        GlobalPlugin(),
        "module_name = ?",
        plugin_name,
        default=GlobalPlugin(module_name=plugin_name, enabled=True)).enabled


def get_plugin_can_be_toggle(plugin_name: str) -> bool:
    """
    获取插件是否可以被启用/停用

    Args:
        plugin_name (str): 插件模块名

    Returns:
        bool: 插件是否可以被启用/停用
    """
    plug = nonebot.plugin.get_plugin(plugin_name)
    return plug.metadata.extra.get("toggleable", True) if plug and plug.metadata else True
