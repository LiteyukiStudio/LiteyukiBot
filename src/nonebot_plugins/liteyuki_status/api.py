import platform
import time

import nonebot
import psutil
from cpuinfo import cpuinfo
from nonebot import require
from nonebot.adapters import satori

from src.utils import __NAME__
from liteyuki import __version__
from src.utils.base.config import get_config
from src.utils.base.data_manager import TempConfig, common_db
from src.utils.base.language import Language
from src.utils.base.resource import get_loaded_resource_packs, get_path
from src.utils.message.html_tool import template2image
from src.utils import satori_utils
from .counter_for_satori import satori_counter
from git import Repo

# require("nonebot_plugin_apscheduler")
# from nonebot_plugin_apscheduler import scheduler

commit_hash = Repo(".").head.commit.hexsha

protocol_names = {
    0: "iPad",
    1: "Android Phone",
    2: "Android Watch",
    3: "Mac",
    5: "iPad",
    6: "Android Pad",
}

"""
Universal Interface
data
- bot
  - name: str
    icon: str
    id: int
    protocol_name: str
    groups: int
    friends: int
    message_sent: int
    message_received: int
    app_name: str
- hardware
    - cpu
        - percent: float
        - name: str
    - mem
        - percent: float
        - total: int
        - used: int
        - free: int
    - swap
        - percent: float
        - total: int
        - used: int
        - free: int
    - disk: list
        - name: str
        - percent: float
        - total: int
"""


# status_card_cache = {}  # lang -> bytes


# 60s刷新一次
# 之前写的什么鬼玩意，这么重要的功能这样写？？？
# @scheduler.scheduled_job("cron", second="*/40")
# async def refresh_status_card():
#     nonebot.logger.debug("Refreshing status card cache.")
#     global status_card_cache
#     status_card_cache = {}
# bot_data = await get_bots_data()
# hardware_data = await get_hardware_data()
# liteyuki_data = await get_liteyuki_data()
# for lang in status_card_cache.keys():
#     status_card_cache[lang] = await generate_status_card(
#         bot_data,
#         hardware_data,
#         liteyuki_data,
#         lang=lang,
#         use_cache=False
#     )


# 获取状态卡片
# bot_id 参数已经是bot参数的一部分了，不需要保留，但为了“兼容性”……
async def generate_status_card(
        bot: dict,
        hardware: dict,
        liteyuki: dict,
        lang="zh-CN",
        bot_id="0",
) -> bytes:
    return await template2image(
        get_path("templates/status.html", abs_path=True),
        {
            "data": {
                "bot": bot,
                "hardware": hardware,
                "liteyuki": liteyuki,
                "localization": get_local_data(lang),
            }
        },
    )


def get_local_data(lang_code) -> dict:
    lang = Language(lang_code)
    return {
        "friends": lang.get("status.friends"),
        "groups": lang.get("status.groups"),
        "plugins": lang.get("status.plugins"),
        "bots": lang.get("status.bots"),
        "message_sent": lang.get("status.message_sent"),
        "message_received": lang.get("status.message_received"),
        "cpu": lang.get("status.cpu"),
        "memory": lang.get("status.memory"),
        "swap": lang.get("status.swap"),
        "disk": lang.get("status.disk"),
        "usage": lang.get("status.usage"),
        "total": lang.get("status.total"),
        "used": lang.get("status.used"),
        "free": lang.get("status.free"),
        "days": lang.get("status.days"),
        "hours": lang.get("status.hours"),
        "minutes": lang.get("status.minutes"),
        "seconds": lang.get("status.seconds"),
        "runtime": lang.get("status.runtime"),
        "threads": lang.get("status.threads"),
        "cores": lang.get("status.cores"),
        "process": lang.get("status.process"),
        "resources": lang.get("status.resources"),
        "description": lang.get("status.description"),
    }


async def get_bots_data(self_id: str = "0") -> dict:
    """获取当前所有机器人数据
    Returns:
    """
    result = {
        "self_id": self_id,
        "bots": [],
    }
    for bot_id, bot in nonebot.get_bots().items():
        groups = 0
        friends = 0
        status = {}
        bot_name = bot_id
        version_info = {}
        if isinstance(bot, satori.Bot):
            try:
                bot_name = (await satori_utils.user_infos.get(bot.self_id)).name
                groups = str(await satori_utils.count_groups(bot))
                friends = str(await satori_utils.count_friends(bot))
                status = {}
                version_info = await bot.get_version_info()
            except Exception:
                pass
        else:
            try:
                # API fetch
                bot_name = (await bot.get_login_info())["nickname"]
                groups = len(await bot.get_group_list())
                friends = len(await bot.get_friend_list())
                status = await bot.get_status()
                version_info = await bot.get_version_info()
            except Exception:
                pass

        statistics = status.get("stat", {})
        app_name = version_info.get("app_name", "UnknownImplementation")
        if app_name in ["Lagrange.OneBot", "LLOneBot", "Shamrock", "NapCat.Onebot"]:
            icon = f"https://q.qlogo.cn/g?b=qq&nk={bot_id}&s=640"
        elif isinstance(bot, satori.Bot):
            app_name = "Satori"
            icon = (await bot.login_get()).user.avatar
        else:
            icon = None
        bot_data = {
            "name": bot_name,
            "icon": icon,
            "id": bot_id,
            "protocol_name": protocol_names.get(
                version_info.get("protocol_name"), "Online"
            ),
            "groups": groups,
            "friends": friends,
            "message_sent": (
                satori_counter.msg_sent
                if isinstance(bot, satori.Bot)
                else statistics.get("message_sent", 0)
            ),
            "message_received": (
                satori_counter.msg_received
                if isinstance(bot, satori.Bot)
                else statistics.get("message_received", 0)
            ),
            "app_name": app_name,
        }
        result["bots"].append(bot_data)

    return result


async def get_hardware_data() -> dict:
    mem = psutil.virtual_memory()
    all_processes = psutil.Process().children(recursive=True)
    all_processes.append(psutil.Process())

    mem_used_process = 0
    process_mem = {}
    for process in all_processes:
        try:
            ps_name = process.name().replace(".exe", "")
            if ps_name not in process_mem:
                process_mem[ps_name] = 0
            process_mem[ps_name] += process.memory_info().rss
            mem_used_process += process.memory_info().rss
        except Exception:
            pass
    swap = psutil.swap_memory()
    cpu_brand_raw = cpuinfo.get_cpu_info().get("brand_raw", "Unknown")
    if "amd" in cpu_brand_raw.lower():
        brand = "AMD"
    elif "intel" in cpu_brand_raw.lower():
        brand = "Intel"
    elif "apple" in cpu_brand_raw.lower():
        brand = "Apple"
    elif "qualcomm" in cpu_brand_raw.lower():
        brand = "Qualcomm"
    elif "mediatek" in cpu_brand_raw.lower():
        brand = "MediaTek"
    elif "samsung" in cpu_brand_raw.lower():
        brand = "Samsung"
    elif "nvidia" in cpu_brand_raw.lower():
        brand = "NVIDIA"
    else:
        brand = "Unknown"
    result = {
        "cpu": {
            "percent": psutil.cpu_percent(),
            "name": f"{brand} {cpuinfo.get_cpu_info().get('arch', 'Unknown')}",
            "cores": psutil.cpu_count(logical=False),
            "threads": psutil.cpu_count(logical=True),
            "freq": psutil.cpu_freq().current,  # MHz
        },
        "memory": {
            "percent": mem.percent,
            "total": mem.total,
            "used": mem.used,
            "free": mem.free,
            "usedProcess": mem_used_process,
        },
        "swap": {
            "percent": swap.percent,
            "total": swap.total,
            "used": swap.used,
            "free": swap.free,
        },
        "disk": [],
    }

    for disk in psutil.disk_partitions(all=True):
        try:
            disk_usage = psutil.disk_usage(disk.mountpoint)
            if disk_usage.total == 0 or disk.mountpoint.startswith(
                    ("/var", "/boot", "/run", "/proc", "/sys", "/dev", "/tmp", "/snap")
            ):
                continue  # 虚拟磁盘
            result["disk"].append(
                {
                    "name": disk.mountpoint,
                    "percent": disk_usage.percent,
                    "total": disk_usage.total,
                    "used": disk_usage.used,
                    "free": disk_usage.free,
                }
            )
        except:
            pass

    return result


async def get_liteyuki_data() -> dict:
    temp_data: TempConfig = common_db.where_one(TempConfig(), default=TempConfig())
    result = {
        "name": list(get_config("nickname", [__NAME__]))[0],
        "version": f"{__version__}{'-' + commit_hash[:7] if (commit_hash and len(commit_hash) > 8) else ''}",
        "plugins": len(nonebot.get_loaded_plugins()),
        "resources": len(get_loaded_resource_packs()),
        "nonebot": f"{nonebot.__version__}",
        "python": f"{platform.python_implementation()} {platform.python_version()}",
        "system": f"{platform.system()} {platform.release()}",
        "runtime": time.time()
                   - temp_data.data.get("start_time", time.time()),  # 运行时间秒数
        "bots": len(nonebot.get_bots()),
    }
    return result
