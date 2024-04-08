import json
import os.path
import platform
import sys

import nonebot

__NAME__ = "LiteyukiBot"
__VERSION__ = "6.2.8"  # 60201

import requests

from liteyuki.utils.config import load_from_yaml, config
from .log import init_log
from .data_manager import auto_migrate

major, minor, patch = map(int, __VERSION__.split("."))
__VERSION_I__ = major * 10000 + minor * 100 + patch


def register_bot():
    url = "https://api.liteyuki.icu/register"
    data = {
            "name"     : __NAME__,
            "version"  : __VERSION__,
            "version_i": __VERSION_I__,
            "python"   : f"{platform.python_implementation()} {platform.python_version()}",
            "os"       : f"{platform.system()} {platform.version()} {platform.machine()}"
    }
    try:
        nonebot.logger.info("Waiting for register to Liteyuki...")
        resp = requests.post(url, json=data)
        if resp.status_code == 200:
            data = resp.json()
            if liteyuki_id := data.get("liteyuki_id"):
                with open("data/liteyuki/liteyuki.json", "wb") as f:
                    f.write(json.dumps(data).encode("utf-8"))
                nonebot.logger.success(f"Register {liteyuki_id} to Liteyuki successfully")
            else:
                raise ValueError(f"Register to Liteyuki failed: {data}")

    except Exception as e:
        nonebot.logger.warning(f"Register to Liteyuki failed, but it's no matter: {e}")


def init():
    """
    初始化
    Returns:

    """
    # 检测python版本是否高于3.10
    if sys.version_info < (3, 10):
        nonebot.logger.error("This project requires Python3.10+ to run, please upgrade your Python Environment.")
        exit(1)
    auto_migrate()
    # 在加载完成语言后再初始化日志
    nonebot.logger.info("Liteyuki is initializing...")

    if not os.path.exists("data/liteyuki/liteyuki.json"):
        register_bot()

    nonebot.logger.info(
        f"Run Liteyuki with Python{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} "
        f"at {sys.executable}"
    )
    nonebot.logger.info(f"{__NAME__} {__VERSION__}({__VERSION_I__}) is running")
