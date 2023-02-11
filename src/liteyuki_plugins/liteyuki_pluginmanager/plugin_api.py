import math
import random
from typing import Dict, List

from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.plugin import Plugin
from nonebot.plugin import get_loaded_plugins
from nonebot.plugin.plugin import PluginMetadata
from nonebot.utils import run_sync

from ...liteyuki_api.canvas import *
from ...liteyuki_api.data import Data
from ...liteyuki_api.resource import Font
from ...liteyuki_api.utils import generate_signature

metadata_db = Data(Data.globals, "plugin_metadata")


async def search_for_plugin_by_liteyuki(keyword: str) -> Union[Plugin, None]:
    """
    模糊搜索插件.会给插件强行生成元数据

    :param keyword: 搜索关键词
    :return:
    """
    # 精准搜搜
    for p in await get_loaded_plugin_by_liteyuki():
        """关键词==插件id名"""
        if keyword == p.name or keyword == p.metadata.name:
            return p
    # 模糊搜索
    for p in await get_loaded_plugin_by_liteyuki():
        if keyword in p.name or keyword in p.metadata.name:
            return p
    return None


async def get_plugin_by_liteyuki(plugin_id) -> Plugin:
    """
    通过插件名获取插件
    :param plugin_id:
    :return:
    """
    for _plugin in await get_loaded_plugin_by_liteyuki():
        if _plugin.name == plugin_id:
            return _plugin


async def get_loaded_plugin_by_liteyuki() -> List[Plugin]:
    """
    获取插件列表
    顺便给插件自动添加元数据

    :return:
    """
    plugin_list = []
    for _plugin in get_loaded_plugins():
        if _plugin.metadata is None:
            metadata_base = {
                "name": "",
                "description": "",
                "usage": ""
            }
            custom_metadata = await metadata_db.get(_plugin.name)
            if custom_metadata is not None:
                metadata_base.update(custom_metadata)
                _plugin.metadata = PluginMetadata(**metadata_base)
            else:
                _plugin.metadata = PluginMetadata(
                    name=_plugin.name,
                    description="无",
                    usage="无",
                    extra={
                        "no_metadata": True
                    }
                )
        plugin_list.append(_plugin)
    return plugin_list


async def get_plugin_default_stats(plugin_name) -> bool:
    plugin = await search_for_plugin_by_liteyuki(plugin_name)
    default_enable = plugin.metadata.extra.get("default_enable", True)
    return default_enable


async def check_enabled_stats(event: Union[GroupMessageEvent, PrivateMessageEvent], plugin_id) -> bool:
    """
    检查返回插件是否启用
    :param event: 会话
    :param plugin_id:
    :return:
    """
    db = Data(*Data.get_type_id(event))
    enabled_plugin = await db.get("enabled_plugin", [])
    disabled_plugin = await db.get("disabled_plugin", [])
    default_enable = await get_plugin_default_stats(plugin_id)
    if default_enable and plugin_id not in disabled_plugin or not default_enable and plugin_id in enabled_plugin:
        return True
    else:
        return False


async def generate_plugin_image(event) -> Canvas:
    """排序，把轻雪插件排到前面来"""
    loaded_plugins = await get_loaded_plugin_by_liteyuki()
    """隐藏的插件列表"""
    hidden_plugins_store = await Data(Data.globals, "plugin_data").get("hidden_plugin", [])
    """实际上加载的隐藏插件"""
    hidden_plugins_loaded = []
    """待排序后将加载且可视列表加入其中"""
    loaded_plugins_visible_sorted = []
    """先遍历全部，排轻雪插件"""
    for _plugin in loaded_plugins:
        if _plugin.name in hidden_plugins_store:
            hidden_plugins_loaded.append(_plugin)
        if _plugin.metadata.extra.get("liteyuki_plugin", False) and _plugin.name not in hidden_plugins_store:
            loaded_plugins_visible_sorted.append(_plugin)
    """再排其他插件"""
    for _plugin in loaded_plugins:
        if _plugin.metadata.extra.get("liteyuki_plugin", False):
            pass
        else:
            if _plugin.name not in hidden_plugins_store:
                loaded_plugins_visible_sorted.append(_plugin)
    visible_plugin_count = len(loaded_plugins_visible_sorted)
    count_for_each_line = math.ceil(visible_plugin_count / 28)
    """每行插件数"""
    show_line_count = math.ceil(visible_plugin_count / count_for_each_line)
    """展示行数"""
    random.choice(["FFEC82F6", "FF82D1F6", "FF82F6A7", "FFF4F682"])
    """随机背景色"""
    base_fillet = 10
    """基础圆角值"""
    base_fillet_2 = 5
    """基础圆角值2"""
    width = 1600
    """底图宽度"""
    head_height = 600
    """头块高度"""
    block_distance = 15
    """头身间隔高度"""
    plugin_line_height = 100
    """插件每行高"""
    side_width = 20
    """边缘宽度"""
    plugin_block_distance = 10
    """插件块横纵间隔"""
    width -= 2 * side_width
    """内容区实际宽度"""
    tips_height = 120
    """提示区宽度"""
    base_gray = (40, 40, 40, 168)
    plugins_block_height = show_line_count * plugin_line_height + (show_line_count + 1) * plugin_block_distance
    normal_font = Font.MiSans_Demibold
    heavy_font = Font.MiSans_Heavy
    base_img_size = (width + 2 * side_width,
                     side_width * 2 + block_distance * 2 + head_height + tips_height + plugins_block_height)
    drawing_path = os.path.join(Path.data, "liteyuki/drawing")
    if len(os.listdir(drawing_path)) > 0:
        base_img = Utils.central_clip_by_ratio(Image.open(os.path.join(Path.data, "liteyuki/drawing/%s" % random.choice(os.listdir(drawing_path)))), base_img_size)
    else:
        base_img = Image.new(mode="RGBA", size=base_img_size, color=(255, 255, 255, 255))
    help_canvas = Canvas(
        base_img
    )
    # help_canvas.bg = Img(
    #     uv_size=help_canvas.base_img.size, box_size=(help_canvas.base_img.size[0] - 2 * side_width, help_canvas.base_img.size[1] - 2 * side_width),
    #     parent_point=(0.5, 0.5), point=(0.5, 0.5)
    # )
    help_canvas.content = Panel(uv_size=help_canvas.base_img.size, box_size=(help_canvas.base_img.size[0] - 2 * side_width, help_canvas.base_img.size[1] - 2 * side_width),
                                parent_point=(0.5, 0.5), point=(0.5, 0.5))
    content_size = help_canvas.get_actual_pixel_size("content")
    help_canvas.content.head = Rectangle(uv_size=(1, 1), box_size=(1, head_height / content_size[1]),
                                         parent_point=(0.5, 0), point=(0.5, 0), color=base_gray, fillet=base_fillet)
    help_canvas.content.head.title = Text(uv_size=(1, 1), box_size=(1, 0.2), parent_point=(0.5, 0.35), point=(0.5, 0.5), text="LiteyukiBot插件列表/菜单", font=heavy_font)
    help_canvas.content.head.tips = Text(
        uv_size=(1, 1), box_size=(0.5, 0.1), parent_point=(0.01, 0.98), point=(0, 1), font=normal_font, color=(255, 255, 255, 255),
        text=[
            TextSegment("绿色:轻雪插件    ", color=Color.GREEN), TextSegment("白色:第三方插件")
        ]
    )
    help_canvas.content.head.liteyuki_sign = Text(uv_size=(1, 1), box_size=(1, 0.1), parent_point=(0.99, 0.995), point=(1, 1), text=generate_signature, font=heavy_font,
                                                  color=(200, 200, 200, 255))
    head_pos = help_canvas.get_parent_box("content.head")

    # 提示区块

    help_canvas.content.tips = Rectangle(uv_size=(1, 1), box_size=(1, tips_height / content_size[1]),
                                         parent_point=(head_pos[0], head_pos[3] + block_distance / content_size[1]), point=(0, 0), color=base_gray,
                                         fillet=base_fillet, keep_ratio=False)
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
        uv_size=(1, 1), box_size=(1, plugins_block_height / content_size[1]),
        parent_point=(tips_pos[0], tips_pos[3] + block_distance / content_size[1]), point=(0, 0)
    )
    help_canvas.content.plugins.img = Rectangle(
        uv_size=(1, 1), box_size=(1, 1), parent_point=(0, 0), point=(0, 0), img=None, keep_ratio=False, fillet=base_fillet, color=(40, 40, 40, 192)
    )

    plugins_size = help_canvas.get_actual_pixel_size("content.plugins.img")
    plugin_block_width = int((plugins_size[0] - (count_for_each_line + 1) * plugin_block_distance) / count_for_each_line)
    for plugin_i, plugin in enumerate(loaded_plugins_visible_sorted):
        plugin_show_name = plugin.metadata.name
        """行数,0开始"""
        row = plugin_i // count_for_each_line
        """列数,0开始"""
        columns = plugin_i % count_for_each_line

        x0 = (plugin_block_distance + columns * (plugin_block_distance + plugin_block_width)) / plugins_size[0]
        y0 = (plugin_block_distance + row * (plugin_block_distance + plugin_line_height)) / plugins_size[1]
        rec_color = (0, 0, 0, 40 if row % 2 == 0 else 120)
        """单个插件圆角底图"""
        plugin_bg = help_canvas.content.plugins.__dict__["plugin_bg_%s" % plugin_i] = Rectangle(
            uv_size=plugins_size, box_size=(plugin_block_width, plugin_line_height), parent_point=(x0, y0), point=(0, 0), fillet=base_fillet_2, color=rec_color,
            keep_ratio=False
        )
        """轻雪插件为绿字"""
        color = Color.GREEN if plugin.metadata is not None and plugin.metadata.extra.get("liteyuki_plugin", False) else Color.WHITE
        """原神类插件为特殊字体"""
        font = Font.MiSans_Medium
        """插件开关"""
        state = await check_enabled_stats(event, plugin.name)
        plugin_bg.plugin_stats_img = Img(
            uv_size=(1, 1), box_size=(0.3, 0.6), parent_point=(0.975, 0.5), point=(1, 0.5),
            img=Image.open(os.path.join(Path.res, f"textures/liteyuki/state_{'on' if state else 'off'}.png"))
        )
        """开关位置"""
        plugin_bg.plugin_name = Text(
            uv_size=(1, 1), box_size=(0.67, 0.5), parent_point=(0.025, 0.5), point=(0, 0.5), text=plugin.metadata.name, font=font, color=color, dp=1,
        )

    return help_canvas


async def search_plugin_info_online(plugin_name, search_list=None) -> List[Dict] | None:
    """
    在线搜索插件信息，返回搜索结果列表
    :param search_list: 搜索列表，建议多插件安装时直接传入
    :param plugin_name:
    :return:[{"name": "插件名称", "id": "nonebot-plugin-name", “description”: "插件描述"}] 或 None
    """
    data = []
    plugin_name = plugin_name.replace("-", "_")
    if search_list is None:
        search_list = await get_online_plugin_list()
    for plugin_data in search_list:
        if plugin_name in plugin_data["name"] or plugin_name in plugin_data["id"].replace("-", "_") or plugin_name in plugin_data["description"]:
            data.append(plugin_data)
    if len(data) > 0:
        return data
    else:
        return None


async def get_online_plugin_list() -> List[Dict] | None:
    """
    获取商店在线插件列表
    :return:[{"name": "插件名", "id": "nonebot-plugin-name", “description”: "插件描述"}]
    """
    lines = []
    data = []
    res = await run_sync(os.popen)("nb plugin list")
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
