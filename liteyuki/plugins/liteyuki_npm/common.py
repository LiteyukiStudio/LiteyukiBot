import json
from typing import Optional

import aiofiles
import nonebot.plugin

from liteyuki.utils.data import Database, LiteModel
from liteyuki.utils.data_manager import Group, InstalledPlugin, User, group_db, plugin_db, user_db
from liteyuki.utils.ly_typing import T_MessageEvent

LNPM_COMMAND_START = "lnpm"


class PluginTag(LiteModel):
    label: str
    color: str = '#000000'


class StorePlugin(LiteModel):
    name: str
    desc: str
    module_name: str
    project_link: str = ""
    homepage: str =""
    author: str = ""
    type: str | None = None
    version: str | None = ""
    time: str = ""
    tags: list[PluginTag] = []
    is_official: bool = False


async def get_store_plugin(plugin_module_name: str) -> Optional[StorePlugin]:
    """
    获取插件信息

    Args:
        plugin_module_name (str): 插件模块名

    Returns:
        Optional[StorePlugin]: 插件信息
    """
    async with aiofiles.open("data/liteyuki/plugins.json", "r", encoding="utf-8") as f:
        plugins: list[StorePlugin] = [StorePlugin(**pobj) for pobj in json.loads(await f.read())]
    for plugin in plugins:
        if plugin.module_name == plugin_module_name:
            return plugin
    return None


def get_plugin_default_enable(plugin_module_name: str) -> bool:
    """
    获取插件默认启用状态，由插件定义，不存在则默认为启用

    Args:
        plugin_module_name (str): 插件模块名

    Returns:
        bool: 插件默认状态
    """
    plug = nonebot.plugin.get_plugin_by_module_name(plugin_module_name)
    return (plug.metadata.extra.get("default_enable", True)
            if plug.metadata else True) if plug else True


def get_plugin_session_enable(event: T_MessageEvent, plugin_module_name: str) -> bool:
    """
    获取插件当前会话启用状态

    Args:
        event: 会话事件
        plugin_module_name (str): 插件模块名

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
    default_enable = get_plugin_default_enable(plugin_module_name)
    if default_enable:
        return plugin_module_name not in session.disabled_plugins
    else:
        return plugin_module_name in session.enabled_plugins


def get_plugin_global_enable(plugin_module_name: str) -> bool:
    return plugin_db.first(
        InstalledPlugin(),
        "module_name = ?",
        plugin_module_name,
        default=InstalledPlugin(module_name=plugin_module_name, enabled=True)).enabled


def get_plugin_can_be_toggle(plugin_module_name: str) -> bool:
    """
    获取插件是否可以被启用/停用

    Args:
        plugin_module_name (str): 插件模块名

    Returns:
        bool: 插件是否可以被启用/停用
    """
    plug = nonebot.plugin.get_plugin_by_module_name(plugin_module_name)
    return plug.metadata.extra.get("toggleable", True) if plug and plug.metadata else True
