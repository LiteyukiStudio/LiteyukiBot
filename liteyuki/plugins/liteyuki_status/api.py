import platform
import time

import nonebot
import psutil
from cpuinfo import cpuinfo
from liteyuki.utils import __NAME__, __VERSION__
from liteyuki.utils.base.config import get_config
from liteyuki.utils.base.data_manager import TempConfig, common_db
from liteyuki.utils.base.language import Language
from liteyuki.utils.base.resource import get_path
from liteyuki.utils.message.html_tool import template2image

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


async def generate_status_card(bot: dict, hardware: dict, liteyuki: dict, lang="zh-CN", bot_id="0") -> bytes:
    return await template2image(
        get_path("templates/status.html", abs_path=True),
        {
                "data": {
                        "bot"         : bot,
                        "hardware"    : hardware,
                        "liteyuki"    : liteyuki,
                        "localization": get_local_data(lang)
                }
        },
        debug=True
    )


def get_local_data(lang_code) -> dict:
    lang = Language(lang_code)
    return {
            "friends"         : lang.get("status.friends"),
            "groups"          : lang.get("status.groups"),
            "plugins"         : lang.get("status.plugins"),
            "bots"            : lang.get("status.bots"),
            "message_sent"    : lang.get("status.message_sent"),
            "message_received": lang.get("status.message_received"),
            "cpu"             : lang.get("status.cpu"),
            "memory"          : lang.get("status.memory"),
            "swap"            : lang.get("status.swap"),
            "disk"            : lang.get("status.disk"),

            "usage"           : lang.get("status.usage"),
            "total"           : lang.get("status.total"),
            "used"            : lang.get("status.used"),
            "free"            : lang.get("status.free"),

            "days"            : lang.get("status.days"),
            "hours"           : lang.get("status.hours"),
            "minutes"         : lang.get("status.minutes"),
            "seconds"         : lang.get("status.seconds"),
            "runtime"         : lang.get("status.runtime"),

    }


async def get_bots_data(self_id: str = "0") -> dict:
    """获取当前所有机器人数据
    Returns:
    """
    result = {
            "self_id": self_id,
            "bots"   : [],
    }
    for bot_id, bot in nonebot.get_bots().items():
        groups = 0
        friends = 0
        status = {}
        bot_name = bot_id
        version_info = {}
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
        if app_name in ["Lagrange.OneBot", "LLOneBot", "Shamrock"]:
            icon = f"https://q.qlogo.cn/g?b=qq&nk={bot_id}&s=640"
        else:
            icon = None
        bot_data = {
                "name"            : bot_name,
                "icon"            : icon,
                "id"              : bot_id,
                "protocol_name"   : protocol_names.get(version_info.get("protocol_name"), "Online"),
                "groups"          : groups,
                "friends"         : friends,
                "message_sent"    : statistics.get("message_sent", 0),
                "message_received": statistics.get("message_received", 0),
                "app_name"        : app_name
        }
        result["bots"].append(bot_data)

    return result


async def get_hardware_data() -> dict:
    mem = psutil.virtual_memory()
    all_processes = psutil.Process().children(recursive=True)
    all_processes.append(psutil.Process())

    mem_used_bot = 0
    process_mem = {}
    for process in all_processes:
        try:
            ps_name = process.name().replace(".exe", "")
            if ps_name not in process_mem:
                process_mem[ps_name] = 0
            process_mem[ps_name] += process.memory_info().rss
            mem_used_bot += process.memory_info().rss
        except Exception:
            pass
    swap = psutil.swap_memory()
    cpu_brand_raw = cpuinfo.get_cpu_info().get("brand_raw", "Unknown")
    if "AMD" in cpu_brand_raw:
        brand = "AMD"
    elif "Intel" in cpu_brand_raw:
        brand = "Intel"
    else:
        brand = "Unknown"
    result = {
            "cpu" : {
                    "percent": psutil.cpu_percent(),
                    "name"   : f"{brand} {cpuinfo.get_cpu_info().get('arch', 'Unknown')}",
                    "cores"  : psutil.cpu_count(logical=False),
                    "threads": psutil.cpu_count(logical=True),
                    "freq"   : psutil.cpu_freq().current    # MHz
            },
            "memory" : {
                    "percent": mem.percent,
                    "total"  : mem.total,
                    "used"   : mem.used,
                    "free"   : mem.free,
            },
            "swap": {
                    "percent": swap.percent,
                    "total"  : swap.total,
                    "used"   : swap.used,
                    "free"   : swap.free
            },
            "disk": [],
    }

    for disk in psutil.disk_partitions(all=True):
        try:
            disk_usage = psutil.disk_usage(disk.mountpoint)
            result["disk"].append({
                    "name"   : disk.mountpoint,
                    "percent": disk_usage.percent,
                    "total"  : disk_usage.total,
                    "used"   : disk_usage.used,
                    "free"   : disk_usage.free
            })
        except:
            pass

    return result


async def get_liteyuki_data() -> dict:
    temp_data: TempConfig = common_db.first(TempConfig(), default=TempConfig())
    result = {
            "name"   : list(get_config("nickname", [__NAME__]))[0],
            "version": __VERSION__,
            "plugins": len(nonebot.get_loaded_plugins()),
            "nonebot": f"{nonebot.__version__}",
            "python" : f"{platform.python_implementation()} {platform.python_version()}",
            "system" : f"{platform.system()} {platform.release()}",
            "runtime": time.time() - temp_data.data.get("start_time", time.time()),  # 运行时间秒数
            "bots"   : len(nonebot.get_bots())
    }
    return result
