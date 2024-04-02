import platform

import nonebot
import psutil
from cpuinfo import get_cpu_info
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.permission import SUPERUSER

from liteyuki.utils import __NAME__, __VERSION__
from liteyuki.utils.htmlrender import template2image
from liteyuki.utils.language import get_user_lang
from liteyuki.utils.ly_typing import T_Bot, T_MessageEvent
from liteyuki.utils.resource import get_path
from liteyuki.utils.tools import convert_size

stats = on_command("stats", aliases={"状态"}, priority=5, permission=SUPERUSER)

protocol_names = {
        0: "iPad",
        1: "Android Phone",
        2: "Android Watch",
        3: "Mac",
        5: "iPad",
        6: "Android Pad",
}


@stats.handle()
async def _(bot: T_Bot, event: T_MessageEvent):
    ulang = get_user_lang(str(event.user_id))
    fake_device_info: dict = bot.config.dict().get("fake_device_info", {})
    mem_total = fake_device_info.get('mem', {}).get('total', psutil.virtual_memory().total)

    mem_used_bot = psutil.Process().memory_info().rss
    mem_used_other = psutil.virtual_memory().used - mem_used_bot
    mem_free = mem_total - mem_used_other - mem_used_bot

    groups = len(await bot.get_group_list())
    friends = len(await bot.get_friend_list())

    status = await bot.get_status()
    statistics = status.get("stat", {})
    version_info = await bot.get_version_info()

    cpu_info = get_cpu_info()
    if "AMD" in cpu_info.get("brand_raw", ""):
        brand = "AMD"
    elif "Intel" in cpu_info.get("brand_raw", ""):
        brand = "Intel"
    else:
        brand = "Unknown"

    if fake_device_info.get("cpu", {}).get("brand"):
        brand = fake_device_info.get("cpu", {}).get("brand")

    cpu_info = get_cpu_info()
    templ = {
            "CPUDATA"  : [
                    {
                            "name" : "USED",
                            "value": psutil.cpu_percent(interval=1)
                    },
                    {
                            "name" : "FREE",
                            "value": 100 - psutil.cpu_percent(interval=1)
                    }
            ],
            "MEMDATA"  : [

                    {
                            "name" : "OTHER",
                            "value": mem_used_other
                    },
                    {
                            "name" : "FREE",
                            "value": mem_free
                    },
                    {
                            "name" : "BOT",
                            "value": mem_used_bot
                    },
            ],
            "SWAPDATA" : [
                    {
                            "name" : "USED",
                            "value": psutil.swap_memory().used
                    },
                    {
                            "name" : "FREE",
                            "value": psutil.swap_memory().free
                    }
            ],
            "BOT_ID"   : bot.self_id,
            "BOT_NAME" : (await bot.get_login_info())["nickname"],
            "BOT_TAGS" : [
                    protocol_names.get(version_info.get("protocol_name"), "Online"),
                    f"{ulang.get('liteyuki.stats.plugins')} {len(nonebot.get_loaded_plugins())}",
                    f"{ulang.get('liteyuki.stats.groups')} {groups}",
                    f"{ulang.get('liteyuki.stats.friends')} {friends}",
                    f"{ulang.get('liteyuki.stats.sent')} {statistics.get('message_sent', 0)}",
                    f"{ulang.get('liteyuki.stats.received')} {statistics.get('message_received', 0)}",
                    f"{__NAME__} {__VERSION__}",
                    f"Nonebot {nonebot.__version__}",
                    f"{platform.python_implementation()} {platform.python_version()}",
                    version_info.get("app_name"),
            ],
            "CPU_TAGS" : [
                    f"{brand} {cpu_info.get('arch', 'Unknown')}",
                    f"{fake_device_info.get('cpu', {}).get('cores', psutil.cpu_count(logical=False))}C "
                    f"{fake_device_info.get('cpu', {}).get('logical_cores', psutil.cpu_count(logical=True))}T",
                    f"{fake_device_info.get('cpu', {}).get('frequency', psutil.cpu_freq().current) / 1000}GHz"
            ],
            "MEM_TAGS" : [
                    f"Bot {convert_size(mem_used_bot, 1)}",
                    f"{ulang.get('main.monitor.used')} {convert_size(mem_used_other + mem_used_bot, 1)}",
                    f"{ulang.get('main.monitor.total')} {convert_size(mem_total, 1)}",
            ],
            "SWAP_TAGS": [
                    f"{ulang.get('main.monitor.used')} {convert_size(psutil.swap_memory().used, 1)}",
                    f"{ulang.get('main.monitor.total')} {convert_size(psutil.swap_memory().total, 1)}",
            ],
            "CPU"      : ulang.get("main.monitor.cpu"),
            "MEM"      : ulang.get("main.monitor.memory"),
            "SWAP"     : ulang.get("main.monitor.swap"),
    }
    image_bytes = await template2image(
        template=get_path("templates/stats.html", abs_path=True),
        templates=templ,
        scale_factor=4,
    )
    # await md.send_image(image_bytes, bot, event=event)
    await stats.finish(MessageSegment.image(image_bytes))
