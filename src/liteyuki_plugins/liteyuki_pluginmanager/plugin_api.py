import math
import random
from typing import Union, Dict

from ...liteyuki_api.data import Data
from ...liteyuki_api.canvas import *
from nonebot.plugin import Plugin
from nonebot.plugin.plugin import plugins, PluginMetadata
from nonebot.plugin import get_loaded_plugins
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, MessageSegment

from ...liteyuki_api.resource import Font

metadata_db = Data(Data.globals, "plugin_metadata")


def search_for_plugin(keyword: str) -> Union[Plugin, None]:
    """
    模糊搜索插件

    :param keyword: 搜索关键词
    :return:
    """
    # 精准搜搜
    for p in get_loaded_plugins():
        """关键词==插件id名"""
        if keyword == p.name:
            return p
        # 关键词==配置插件名
        elif p.metadata is not None:
            if keyword == p.metadata.name:
                return p
        # 关键词==自定义元数据插件名
        elif metadata_db.get_data(p.name) is not None:
            if keyword == PluginMetadata(**metadata_db.get_data(p.name)).name:
                return p

    # 模糊搜索
    for p in get_loaded_plugins():
        if keyword in p.name:
            return p
        elif p.metadata is not None:
            if keyword in p.metadata.name:
                return p
        elif metadata_db.get_data(p.name) is not None:
            if keyword in PluginMetadata(**metadata_db.get_data(p.name)).name:
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


def generate_plugin_image(event) -> Canvas:
    """排序，把轻雪插件排到前面来"""
    loaded_plugins = get_loaded_plugins()

    hidden_plugins_store = Data(Data.globals, "plugin_data").get_data("hidden_plugin", [])
    hidden_plugins_loaded = []
    loaded_plugins_sorted = []
    for _plugin in loaded_plugins:
        if _plugin.name in hidden_plugins_store:
            hidden_plugins_loaded.append(_plugin)
        if _plugin.metadata is not None and _plugin.metadata.extra.get("liteyuki_plugin", False) and _plugin.name not in hidden_plugins_store:
            loaded_plugins_sorted.append(_plugin)
    for _plugin in loaded_plugins:
        if _plugin.metadata is not None and _plugin.metadata.extra.get("liteyuki_plugin", False):
            pass
        else:
            if _plugin.name not in hidden_plugins_store:
                loaded_plugins_sorted.append(_plugin)
    plugin_count = len(loaded_plugins_sorted)
    """每行有多少插件"""
    count_for_each_line = math.ceil(plugin_count / 20) + 1
    """展示了多少行插件"""
    show_line_count = math.ceil(plugin_count / count_for_each_line)
    bg_color = random.choice(["FFEC82F6", "FF82D1F6", "FF82F6A7", "FFF4F682"])
    base_fillet = 10
    base_fillet_2 = 5
    width = 1600
    head_height = 600
    block_distance = 20
    line_height = 100
    side_width = 15
    """插件块横纵间隔"""
    plugin_block_distance = 10
    content_width = width - 2 * side_width
    tips_height = 120
    normal_font = os.path.join(Path.res, "fonts/MiSans-Demibold.ttf")
    heavy_font = os.path.join(Path.res, "fonts/MiSans-Heavy.ttf")
    help_canvas = Canvas(
        Image.new("RGBA",
                  (width + 2 * side_width, side_width * 2 + head_height + tips_height + block_distance * 2 + (show_line_count + 1) * plugin_block_distance + show_line_count * line_height),
                  Color.hex2dec(bg_color)))
    # help_canvas.bg = Img(
    #     uv_size=help_canvas.base_img.size, box_size=(help_canvas.base_img.size[0] - 2 * side_width, help_canvas.base_img.size[1] - 2 * side_width),
    #     parent_point=(0.5, 0.5), point=(0.5, 0.5)
    # )
    help_canvas.content = Panel(uv_size=help_canvas.base_img.size, box_size=(help_canvas.base_img.size[0] - 2 * side_width, help_canvas.base_img.size[1] - 2 * side_width),
                                parent_point=(0.5, 0.5), point=(0.5, 0.5))
    content_size = help_canvas.get_actual_pixel_size("content")
    help_canvas.content.head = Rectangle(uv_size=(1, 1), box_size=(content_width / width, head_height / help_canvas.base_img.size[1]),
                                         parent_point=(0.5, side_width / help_canvas.base_img.size[1]), point=(0.5, 0), color=(0, 0, 0, 80), fillet=base_fillet)
    help_canvas.content.head.title = Text(uv_size=(1, 1), box_size=(1, 0.2), parent_point=(0.5, 0.35), point=(0.5, 0.5), text="LiteyukiBot插件列表/菜单", font=heavy_font)
    help_canvas.content.head.tips = Text(
        uv_size=(1, 1), box_size=(0.5, 0.1), parent_point=(0.01, 0.98), point=(0, 1), font=normal_font, color=(255, 255, 255, 255),
        text=[
            TextSegment("绿色:轻雪插件    ", color=Color.GREEN), TextSegment("白色:第三方插件")
        ]
    )
    help_canvas.content.head.liteyuki_sign = Text(uv_size=(1, 1), box_size=(1, 0.1), parent_point=(0.99, 0.995), point=(1, 1), text="Generated by LiteyukiBot4.0", font=heavy_font,
                                                  color=(80, 80, 80, 255))
    head_pos = help_canvas.get_parent_box("content.head")

    # 提示区块

    help_canvas.content.tips = Rectangle(uv_size=(1, 1), box_size=(content_width / width, tips_height / help_canvas.base_img.size[1]),
                                         parent_point=(head_pos[0], head_pos[3] + block_distance / help_canvas.base_img.size[1]), point=(0, 0), color=(0, 0, 0, 80),
                                         fillet=base_fillet)
    # 已加载插件
    help_canvas.content.tips.loaded_plugin = Rectangle(
        uv_size=(1, 1), box_size=(0.6, 1), parent_point=(0, 0), point=(0, 0), color=(0, 0, 0, 80), fillet=base_fillet
    )
    help_canvas.content.tips.loaded_plugin.text = Text(
        uv_size=(1, 1), box_size=(10, 0.5), parent_point=(0.5, 0.5), point=(0.5, 0.5), color=(255, 255, 255, 255), font=Font.MiSans_Demibold,
        text=[TextSegment("已加载%s个插件" % len(loaded_plugins)), TextSegment("    隐藏%s个" % len(hidden_plugins_loaded))],
    )
    font_size = help_canvas.get_control_by_path("content.tips.loaded_plugin.text").font_size
    # 提示使用方法
    help_canvas.content.tips.text = Text(
        uv_size=(1, 1), box_size=(0.7, 0.5), parent_point=(0.975, 0.5), point=(1, 0.5), color=(255, 255, 255, 255), font=normal_font,
        text=[TextSegment("发送"), TextSegment("help插件名", color=Color.CYAN), TextSegment("获取详情")], force_size=True, font_size=font_size
    )

    """插件块之间的距离"""
    tips_pos = help_canvas.get_parent_box("content.tips")

    help_canvas.content.plugins = Panel(
        uv_size=(1, 1), box_size=(content_width / width, (line_height * show_line_count + plugin_block_distance * (show_line_count + 1)) / content_size[1]),
        parent_point=(tips_pos[0], tips_pos[3] + block_distance / help_canvas.base_img.size[1]), point=(0, 0)
    )
    help_canvas.content.plugins.img = Rectangle(
        uv_size=(1, 1), box_size=(1, 1), parent_point=(0, 0), point=(0, 0), img=None, keep_ratio=False, fillet=base_fillet
    )

    plugin_block_width = int((content_width - (count_for_each_line + 1) * plugin_block_distance) / count_for_each_line)
    plugin_block_high = line_height
    plugin_font_size = 10
    for i, plugin in enumerate(loaded_plugins_sorted):
        plugin_show_name = plugin.name
        if plugin.metadata is not None:
            plugin_show_name = plugin.metadata.name
        if metadata_db.get_data(plugin.name) is not None:
            plugin_show_name = PluginMetadata(**metadata_db.get_data(plugin.name)).name
        """行数,0开始"""
        row = i // count_for_each_line
        """列数,0开始"""
        columns = i % count_for_each_line
        plugins_size = help_canvas.get_actual_pixel_size("content.plugins")
        x0 = (plugin_block_distance + columns * (plugin_block_distance + plugin_block_width)) / plugins_size[0]
        y0 = (plugin_block_distance + row * (plugin_block_distance + plugin_block_high)) / plugins_size[1]
        rec_color = (0, 0, 0, 148) if row % 2 == 0 else (0, 0, 0, 192)
        plugin_bg = help_canvas.content.plugins.__dict__["plugin_bg_%s" % i] = Rectangle(
            uv_size=plugins_size, box_size=(plugin_block_width, plugin_block_high), parent_point=(x0, y0), point=(0, 0), fillet=base_fillet_2, color=rec_color,
            keep_ratio=False
        )
        color = Color.GREEN if plugin.metadata is not None and plugin.metadata.extra.get("liteyuki_plugin", False) else Color.WHITE
        if "原神" in plugin_show_name + plugin.name or "genshin" in plugin_show_name.lower() + plugin.name.lower():
            font = Font.HYWH_85w
        else:
            font = Font.MiSans_Medium
        plugin_bg.plugin_name = Text(
            uv_size=(1, 1), box_size=(0.8, 0.5), parent_point=(0.05, 0.5), point=(0, 0.5), text=plugin_show_name, font=font, color=color, dp=1, force_size=True,
            font_size=plugin_font_size if i >= 1 else None
        )
        if i == 0:
            plugin_font_size = help_canvas.get_control_by_path("content.plugins.plugin_bg_%s.plugin_name" % i).font_size
        state = check_enabled_stats(event, plugin.name)
        state = "on" if state else "off"
        plugin_bg.plugin_stats_img = Img(
            uv_size=(1, 1), box_size=(0.3, 0.618), parent_point=(0.95, 0.5), point=(1, 0.5), img=Image.open(os.path.join(Path.res, "textures/liteyuki/state_%s.png" % state))
        )
    return help_canvas


def search_plugin_info_online(plugin_name) -> List[Dict] | None:
    """
    在线搜索插件信息

    :param plugin_name:
    :return:
    """
    lines = []
    data = []
    res = os.popen("nb plugin search %s" % plugin_name)
    text = res.read()
    if text == "":
        return None
    else:
        for text_line in text.splitlines():
            if "- " in text_line:
                lines.append(text_line)
            else:
                lines[-1] += text_line
        for plugin_text in lines:
            data.append(
                {
                    "name": plugin_text.split(" (")[0],
                    "description": plugin_text.split("- ")[1],
                    "id": plugin_text.split(" (")[1].split(")")[0],
                }
            )
        return data


def get_online_plugin_list() -> List[Dict] | None:
    """
    获取商店在线插件列表

    :return:
    """
    lines = []
    data = []
    res = os.popen("nb plugin search list")
    text = res.read()
    if text == "":
        return None
    else:
        for text_line in text.splitlines():
            if "- " in text_line:
                lines.append(text_line)
            else:
                lines[-1] += text_line
        for plugin_text in lines:
            data.append(
                {
                    "name": plugin_text.split(" (")[0],
                    "description": plugin_text.split("- ")[1],
                    "id": plugin_text.split(" (")[1].split(")")[0],
                }
            )
        return data
