import datetime
import math
import os
import platform
import random
import time

import psutil
from PIL import Image
from nonebot import get_loaded_plugins
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.utils import run_sync

from .utils import get_usage_percent_color
from ...liteyuki_api.canvas import Img, Text, Utils, TextSegment, Rectangle, Graphical, Panel, Canvas
from ...liteyuki_api.config import config_data, Path
from ...liteyuki_api.data import Data
from ...liteyuki_api.resource import Font
from ...liteyuki_api.utils import time_to_hms_by_sec, generate_signature, download_file, average, size_text, \
    get_text_by_language, clamp


async def generate_state_card(matcher, bot, event):
    if len(bot.config.nickname) == 0:
        bot.config.nickname.add("轻雪")
    stats = await bot.get_status()
    version_info = await bot.get_version_info()
    protocol_dict = {
        -1: "",
        0: "iPad",
        1: await get_text_by_language("10", event.user_id),
        2: await get_text_by_language("11", event.user_id),
        3: "MacOS",
        4: await get_text_by_language("12", event.user_id),
        5: "iPad"
    }
    time_list_6 = [str(i) for i in
                   list(await Data(Data.globals, "liteyuki").get("start_time", tuple(time.localtime())[0:6]))]
    protocol_name = protocol_dict.get(version_info.get("protocol", version_info.get("protocol_name", 0)), "")
    delta_time = datetime.datetime.now() - datetime.datetime.strptime("-".join(time_list_6),
                                                                      "%Y-%m-%d-%H-%M-%S")
    delta_sec = delta_time.days * 86400 + delta_time.seconds
    receive_msg_num = stats.get('stat').get('message_received')
    send_msg_num = stats.get('stat').get('message_sent')
    prop_list = [
        [
            f"{protocol_name}",
            f"{await get_text_by_language('8', event.user_id)} {len(await bot.get_group_list())}",
            f"{await get_text_by_language('9', event.user_id)} {len(await bot.get_friend_list())}"

        ],
        [
            f"{await get_text_by_language('20', event.user_id)} {len(get_loaded_plugins())}",
            f"{await get_text_by_language('21', event.user_id)} {time_to_hms_by_sec(delta_sec)}"
        ],
        [
            f"{await get_text_by_language('22', event.user_id)} {config_data['version_name']}",
            f"{await get_text_by_language('23', event.user_id)} {version_info['app_version']}"
        ]
    ]
    part_3_prop = {
        await get_text_by_language('30', event.user_id): f"{receive_msg_num}/{send_msg_num}",
        await get_text_by_language('31',
                                   event.user_id): f"{stats.get('stat').get('packet_received')}/{stats.get('stat').get('packet_sent')}/{stats.get('stat').get('packet_lost')}",
        "OS": f"{platform.system()}",
        "Python": f"{platform.python_implementation()} {platform.python_version()}",
        "Signature": generate_signature
    }
    drawing_path = os.path.join(Path.data, "liteyuki/drawing")
    head_high = 350
    hardware_high = 700
    block_distance = 20
    block_alpha = 168

    single_disk_high = 70
    disk_distance = 20
    disk_count = len(psutil.disk_partitions())
    part_3_prop_high = 70
    distance_of_part_3_sub_part = 20
    part_3_high = len(part_3_prop) * part_3_prop_high + (
                len(part_3_prop) + 1) * distance_of_part_3_sub_part + disk_distance
    if platform.system() != "Linux":
        part_3_high += disk_distance * disk_count + single_disk_high * disk_count

    width = 1080
    side_up = 20
    side_down = 20

    part_fillet = 20

    default_font = Font.HYWH_85w

    usage_base_color = (192, 192, 192, 192)

    high = side_up + side_down + block_distance * 2 + head_high + hardware_high + part_3_high
    if len(os.listdir(drawing_path)) > 0:
        base_img = await run_sync(Utils.central_clip_by_ratio)(
            Image.open(os.path.join(Path.data, f"liteyuki/drawing/{random.choice(os.listdir(drawing_path))}")),
            (width, high))
    else:
        base_img = Image.new(mode="RGBA", size=(width, high), color=(255, 255, 255, 255))
    info_canvas = Canvas(base_img)
    info_canvas.content = Panel(
        uv_size=info_canvas.base_img.size,
        box_size=(info_canvas.base_img.size[0] - 2 * side_up, info_canvas.base_img.size[1] - side_up - side_down),
        parent_point=(0.5, 0.5), point=(0.5, 0.5)
    )
    content_size = info_canvas.get_actual_pixel_size("content")
    """head block"""
    info_canvas.content.head = Rectangle(
        uv_size=(1, content_size[1]), box_size=(1, head_high),
        parent_point=(0.5, 0), point=(0.5, 0), fillet=part_fillet, color=(0, 0, 0, block_alpha)
    )
    user_icon_path = os.path.join(Path.cache, f"u{bot.self_id}.png")
    await run_sync(download_file)(f"http://q1.qlogo.cn/g?b=qq&nk={bot.self_id}&s=640", user_icon_path, force=True)
    head_size = info_canvas.get_actual_pixel_size("content.head")
    info_canvas.content.head.icon = Img(
        uv_size=(1, 1), box_size=(0.75, 0.75), parent_point=(min(head_size) / 2 / max(head_size), 0.5),
        point=(0.5, 0.5),
        img=await run_sync(Utils.circular_clip)(Image.open(user_icon_path))
    )
    icon_pos = info_canvas.get_parent_box("content.head.icon")
    info_canvas.content.head.nickname = Text(
        uv_size=(1, 1), box_size=(0.6, 0.18), parent_point=(icon_pos[2] + 0.05, 0.23), point=(0, 0.5),
        text=(await bot.get_stranger_info(user_id=event.self_id, no_cache=True))["nickname"], font=default_font, dp=1
    )
    nickname_pos = info_canvas.get_parent_box("content.head.nickname")
    await run_sync(info_canvas.draw_line)("content.head", (nickname_pos[0], nickname_pos[3] + 0.05),
                                          (nickname_pos[2], nickname_pos[3] + 0.05), (255, 255, 255, 255), width=5)
    for i, prop_sub_list in enumerate(prop_list):
        prop_text_list = []
        for prop_str in prop_sub_list:
            prop_text_list.append(TextSegment(prop_str, color=(240, 240, 240, 255)))
            prop_text_list.append(TextSegment(" | ", color=(168, 168, 168, 255)))
        del prop_text_list[-1]
        info_canvas.content.head.__dict__[f"label_{i}"] = Text(
            uv_size=(1, 1), box_size=(0.6, 0.1), parent_point=(nickname_pos[0], nickname_pos[3] + 0.08 + 0.16 * i),
            point=(0, 0), text=prop_text_list, force_size=True, font=default_font
        )
    """hardware block"""
    hardware = info_canvas.content.hardware = Rectangle(
        uv_size=(1, content_size[1]), box_size=(1, hardware_high),
        parent_point=(0.5, (head_high + block_distance) / content_size[1]), point=(0.5, 0), fillet=part_fillet,
        color=(0, 0, 0, block_alpha)
    )

    # percent为0-1的float
    hardware_part = [
        {
            "name": "CPU",
            "percent": psutil.cpu_percent(),
            "sub_prop": [
                f"{await get_text_by_language('40', event.user_id)} {psutil.cpu_count(logical=False)}",
                f"{await get_text_by_language('41', event.user_id)} {psutil.cpu_count()}",
                f"{round(average([percpu.current for percpu in psutil.cpu_freq(percpu=True)]), 1)}MHz"
            ]
        },
        {
            "name": "RAM",
            "percent": psutil.virtual_memory().used / psutil.virtual_memory().total * 100,
            "sub_prop": [
                f"Bot {size_text(psutil.Process(os.getpid()).memory_info().rss)}",
                f"{await get_text_by_language('50', event.user_id)} {size_text(psutil.virtual_memory().used)}",
                f"{await get_text_by_language('51', event.user_id)} {size_text(psutil.virtual_memory().free)}",
                f"{await get_text_by_language('52', event.user_id)} {size_text(psutil.virtual_memory().total)}"
            ]
        }
    ]
    if platform.system() == "Linux":
        hardware_part.append(
            {
                "name": "SWAP",
                "percent": psutil.swap_memory().used / psutil.swap_memory().total * 100
            }
        )
    for part_i, sub_part in enumerate(hardware_part):
        arc_color = get_usage_percent_color(sub_part["percent"])
        point_x = (part_i * 2 + 1) / (len(hardware_part) * 2)
        arc_bg = Graphical.arc(160, 0, 360, width=40, color=usage_base_color)
        arc_up = Graphical.arc(160, 0, 360 * sub_part["percent"] / 100, width=40, color=arc_color)

        part = hardware.__dict__[f"part_{part_i}"] = Panel(
            uv_size=(1, 1), box_size=(1 / len(hardware_part), 1), parent_point=(point_x, 0.4), point=(0.5, 0.5)
        )
        part.arc_bg = Img(uv_size=(1, 1), box_size=(0.6, 0.5), parent_point=(0.5, 0.4), point=(0.5, 0.5), img=arc_bg)

        part.arc_bg.arc_up = Img(uv_size=(1, 1), box_size=(1, 1), parent_point=(0.5, 0.5), point=(0.5, 0.5), img=arc_up)
        part.arc_bg.percent_text = Text(
            uv_size=(1, 1), box_size=(0.54, 0.12), parent_point=(0.5, 0.5), point=(0.5, 0.5),
            text="%.1f" % sub_part["percent"] + "%", font=default_font, dp=1, force_size=True
        )
        arc_pos = info_canvas.get_parent_box(f"content.hardware.part_{part_i}.arc_bg")
        part.name = Text(uv_size=(1, 1), box_size=(1, 0.08), parent_point=(0.5, arc_pos[3] + 0.03), point=(0.5, 0),
                         text=sub_part["name"], force_size=True, font=default_font)
        last_pos = info_canvas.get_parent_box(f"content.hardware.part_{part_i}.name")
        for sub_prop_i, sub_prop in enumerate(sub_part.get("sub_prop", [])):
            part.__dict__[f"sub_prop_{sub_prop_i}"] = Text(
                uv_size=(1, 1), box_size=(1, 0.05), parent_point=(0.5, last_pos[3] + 0.02), point=(0.5, 0),
                text=sub_prop, force_size=True, color=(192, 192, 192, 255), font=default_font
            )
            last_pos = info_canvas.get_parent_box(f"content.hardware.part_{part_i}.sub_prop_{sub_prop_i}")

    part_3 = info_canvas.content.part_3 = Rectangle(
        uv_size=(1, content_size[1]), box_size=(1, part_3_high),
        parent_point=(0.5, (head_high + hardware_high + block_distance * 2) / content_size[1]), point=(0.5, 0),
        fillet=part_fillet, color=(0, 0, 0, block_alpha)
    )
    part_3_pixel_size = info_canvas.get_actual_pixel_size("content.part_3")
    point_y = distance_of_part_3_sub_part / part_3_pixel_size[1]
    if platform.system() != "Linux":
        for disk_i, disk in enumerate(psutil.disk_partitions()):
            try:
                disk_usage = psutil.disk_usage(disk.device)
                disk_panel = part_3.__dict__[f"disk_panel_{disk_i}"] = Panel(
                    uv_size=(1, 1), box_size=(1, single_disk_high / part_3_pixel_size[1]),
                    parent_point=(0.5, point_y + disk_i * (disk_distance + single_disk_high) / part_3_pixel_size[1]),
                    point=(0.5, 0)
                )
                disk_panel.name = Text(
                    uv_size=(1, 1), box_size=(0.2, 0.7), parent_point=(0.05, 0.5), point=(0, 0.5), text=disk.device,
                    font=default_font, force_size=True
                )
                disk_panel.usage_bg = Rectangle(
                    uv_size=(1, 1), box_size=(0.75, 0.9), parent_point=(0.2, 0.5), point=(0, 0.5), fillet=10,
                    color=usage_base_color
                )
                if disk_usage.used > 0:
                    disk_panel.usage_bg.usage_img = Rectangle(
                        uv_size=(1, 1), box_size=(
                            clamp(1 * disk_usage.used / disk_usage.total,
                                  0.1, disk_usage.used / disk_usage.total), 1),
                        parent_point=(0, 0.5), point=(0, 0.5), fillet=10,
                        color=get_usage_percent_color(disk_usage.used / disk_usage.total * 100)
                    )

                disk_panel.usage_bg.usage_text = Text(
                    uv_size=(1, 1), box_size=(1, 0.55), parent_point=(0.5, 0.5), point=(0.5, 0.5),
                    text=f"{round(disk_usage.used / disk_usage.total * 100, 1)}%  {await get_text_by_language('60', event.user_id)} {size_text(disk_usage.free, dec=1)}  "
                         f"{await get_text_by_language('61', event.user_id)} {size_text(disk_usage.total, dec=1)}",
                    font=default_font, dp=1
                )
            except:
                pass
    point_y += (((len(psutil.disk_partitions()) * (
                single_disk_high + disk_distance)) if platform.system() != "Linux" else 0) + distance_of_part_3_sub_part) / \
               part_3_pixel_size[1]
    for prop_i, prop_dict in enumerate(part_3_prop.items()):
        prop_panel = part_3.__dict__[f"prop_panel_{prop_i}"] = Panel(
            uv_size=(1, 1), box_size=(1, part_3_prop_high / part_3_pixel_size[1]),
            parent_point=(
                0.5, point_y + prop_i * (part_3_prop_high + distance_of_part_3_sub_part) / part_3_pixel_size[1]),
            point=(0.5, 0)
        )
        prop_panel.name = Text(
            uv_size=(1, 1), box_size=(0.25, 0.6), parent_point=(0.05, 0.5), point=(0, 0.5), text=prop_dict[0],
            force_size=True, font=default_font
        )
        prop_panel.value = Text(
            uv_size=(1, 1), box_size=(0.25, 0.6), parent_point=(0.95, 0.5), point=(1, 0.5), text=prop_dict[1],
            force_size=True, font=default_font
        )
    await matcher.send(MessageSegment.image(file=f"file:///{await run_sync(info_canvas.export_cache)()}"))
    await run_sync(info_canvas.delete)()
