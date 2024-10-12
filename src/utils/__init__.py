import sys

import nonebot

__NAME__ = "LiteyukiBot"
__VERSION__ = "6.3.2"  # 60201

from src.utils.base.config import load_from_yaml, config
from src.utils.base.log import init_log
from git import Repo

major, minor, patch = map(int, __VERSION__.split("."))
__VERSION_I__ = major * 10000 + minor * 100 + patch


def init():
    """
    初始化
    Returns:

    """
    # 检测python版本是否高于3.10
    init_log()
    if sys.version_info < (3, 10):
        nonebot.logger.error("Requires Python3.10+ to run, please upgrade your Python Environment.")
        exit(1)

    try:
        # 检测git仓库
        repo = Repo(".")
    except Exception as e:
        nonebot.logger.error(f"Failed to load git repository: {e}, please clone this project from GitHub instead of downloading the zip file.")

    # temp_data: TempConfig = common_db.where_one(TempConfig(), default=TempConfig())
    # temp_data.data["start_time"] = time.time()
    # common_db.save(temp_data)

    nonebot.logger.info(
        f"Run Liteyuki-NoneBot with Python{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} "
        f"at {sys.executable}"
    )
    nonebot.logger.info(f"{__NAME__} {__VERSION__}({__VERSION_I__}) is running")
