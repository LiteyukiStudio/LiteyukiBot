import json
from typing import Optional

import aiofiles
import nonebot.plugin
from nonebot.adapters import satori

from src.utils import event as event_utils
from src.utils.base.data import LiteModel
from src.utils.base.data_manager import GlobalPlugin, Group, User, group_db, plugin_db, user_db
from src.utils.base.ly_typing import T_MessageEvent

__group_data = {}  # 群数据缓存, {group_id: Group}
__user_data = {}  # 用户数据缓存, {user_id: User}
__default_enable = {}  # 插件默认启用状态缓存, {plugin_name: bool} static
__global_enable = {}  # 插件全局启用状态缓存, {plugin_name: bool} dynamic


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
    获取插件是否存在于加载列表
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
        if plugin.module_name == plugin_name:
            return plugin
    return None


def get_plugin_default_enable(plugin_name: str) -> bool:
    """
    获取插件默认启用状态，由插件定义，不存在则默认为启用，优先从缓存中获取

    Args:
        plugin_name (str): 插件模块名

    Returns:
        bool: 插件默认状态
    """
    if plugin_name not in __default_enable:
        plug = nonebot.plugin.get_plugin(plugin_name)
        default_enable = (plug.metadata.extra.get("default_enable", True) if plug.metadata else True) if plug else True
        __default_enable[plugin_name] = default_enable

    return __default_enable[plugin_name]


def get_plugin_session_enable(event: T_MessageEvent, plugin_name: str) -> bool:
    """
    获取插件当前会话启用状态

    Args:
        event: 会话事件
        plugin_name (str): 插件模块名

    Returns:
        bool: 插件当前状态
    """
    if isinstance(event, satori.event.Event):
        if event.guild is not None:
            message_type = "group"
        else:
            message_type = "private"
    else:
        message_type = event.message_type
    if message_type == "group":
        group_id = str(event.guild.id if isinstance(event, satori.event.Event) else event.group_id)
        if group_id not in __group_data:
            group: Group = group_db.where_one(Group(), "group_id = ?", group_id, default=Group(group_id=group_id))
            __group_data[str(group_id)] = group

        session = __group_data[group_id]
    else:
        # session: User = user_db.first(User(), "user_id = ?", event.user_id, default=User(user_id=str(event.user_id)))
        user_id = str(event.user.id if isinstance(event, satori.event.Event) else event.user_id)
        if user_id not in __user_data:
            user: User = user_db.where_one(User(), "user_id = ?", user_id, default=User(user_id=user_id))
            __user_data[user_id] = user
        session = __user_data[user_id]
    # 默认停用插件在启用列表内表示启用
    # 默认停用插件不在启用列表内表示停用
    # 默认启用插件在停用列表内表示停用
    # 默认启用插件不在停用列表内表示启用
    default_enable = get_plugin_default_enable(plugin_name)
    if default_enable:
        return plugin_name not in session.disabled_plugins
    else:
        return plugin_name in session.enabled_plugins


def set_plugin_session_enable(event: T_MessageEvent, plugin_name: str, enable: bool):
    """
    设置插件会话启用状态，同时更新数据库和缓存
    Args:
        event:
        plugin_name:
        enable:

    Returns:

    """
    if event_utils.get_message_type(event) == "group":
        session: Group = group_db.where_one(Group(), "group_id = ?", str(event_utils.get_group_id(event)),
                                     default=Group(group_id=str(event_utils.get_group_id(event))))
    else:
        session: User = user_db.where_one(User(), "user_id = ?", str(event_utils.get_user_id(event)),
                                    default=User(user_id=str(event_utils.get_user_id(event))))
    default_enable = get_plugin_default_enable(plugin_name)
    if default_enable:
        if enable:
            session.disabled_plugins.remove(plugin_name)
        else:
            session.disabled_plugins.append(plugin_name)
    else:
        if enable:
            session.enabled_plugins.append(plugin_name)
        else:
            session.enabled_plugins.remove(plugin_name)

    if event_utils.get_message_type(event) == "group":
        __group_data[str(event_utils.get_group_id(event))] = session
        group_db.save(session)
    else:
        __user_data[str(event_utils.get_user_id(event))] = session
        user_db.save(session)


def get_plugin_global_enable(plugin_name: str) -> bool:
    """
    获取插件全局启用状态, 优先从缓存中获取
    Args:
        plugin_name:

    Returns:

    """
    if plugin_name not in __global_enable:
        plugin = plugin_db.where_one(
            GlobalPlugin(),
            "module_name = ?",
            plugin_name,
            default=GlobalPlugin(module_name=plugin_name, enabled=True))
        __global_enable[plugin_name] = plugin.enabled

    return __global_enable[plugin_name]


def set_plugin_global_enable(plugin_name: str, enable: bool):
    """
    设置插件全局启用状态，同时更新数据库和缓存
    Args:
        plugin_name:
        enable:

    Returns:

    """
    plugin = plugin_db.where_one(
        GlobalPlugin(),
        "module_name = ?",
        plugin_name,
        default=GlobalPlugin(module_name=plugin_name, enabled=True))
    plugin.enabled = enable

    plugin_db.save(plugin)
    __global_enable[plugin_name] = enable


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


def get_group_enable(group_id: str) -> bool:
    """
    获取群组是否启用插机器人

    Args:
        group_id (str): 群组ID

    Returns:
        bool: 群组是否启用插件
    """
    group_id = str(group_id)
    if group_id not in __group_data:
        group: Group = group_db.where_one(Group(), "group_id = ?", group_id, default=Group(group_id=group_id))
        __group_data[group_id] = group

    return __group_data[group_id].enable


def set_group_enable(group_id: str, enable: bool):
    """
    设置群组是否启用插机器人

    Args:
        group_id (str): 群组ID
        enable (bool): 是否启用
    """
    group_id = str(group_id)
    group: Group = group_db.where_one(Group(), "group_id = ?", group_id, default=Group(group_id=group_id))
    group.enable = enable

    __group_data[group_id] = group
    group_db.save(group)
