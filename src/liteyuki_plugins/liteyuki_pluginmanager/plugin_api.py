import math
import random
from typing import Union

from ...liteyuki_api.data import Data
from ...liteyuki_api.canvas import *
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


def generate_plugin_image() -> Canvas:
    loaded_plugins = get_loaded_plugins()
    plugin_count = len(loaded_plugins)
    show_line_count = math.ceil(plugin_count / 2)
    bg_color = random.choice(["FFEC82F6", "FF82D1F6", "FF82F6A7", "FFF4F682"])
    width = 800
    head_height = 300
    line_height = 80
    side_width = 20
    content_width = width + 2 * side_width
    hywh_font = os.path.join(Path.res, "fonts/hywh.ttf")
    help_canvas = Canvas(Image.new("RGBA", (width + 2 * side_width, head_height + show_line_count * line_height + 2 * side_width), Color.hex2dec(bg_color)))
    help_canvas.head = Panel(uv_size=(1, 1), box_size=(1, (300 + line_height) / help_canvas.base_img.size[1]), parent_point=(0.5, 0), point=(0.5, 0))
    help_canvas.head.title = Text(uv_size=(1, 1), box_size=(content_width/width, 0.2), parent_point=(0.5, 0.3), point=(0.5, 0.5), text="轻雪插件列表/菜单", font=hywh_font)
    return help_canvas
