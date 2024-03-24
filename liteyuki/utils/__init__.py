import nonebot

from .log import logger
import sys

__NAME__ = "LiteyukiBot"
__VERSION__ = "6.2.1"   # 60201
major, minor, patch = map(int, __VERSION__.split("."))
__VERSION_I__ = major * 10000 + minor * 100 + patch


def init():
    """
    初始化
    Returns:

    """
    # 检测python版本是否高于3.10
    if sys.version_info < (3, 10):
        nonebot.logger.error("This project requires Python3.10+ to run, please upgrade your Python Environment.")
        exit(1)

    print("\033[34m" + r"""
 __        ______  ________  ________  __      __  __    __  __    __  ______ 
/  |      /      |/        |/        |/  \    /  |/  |  /  |/  |  /  |/      |
$$ |      $$$$$$/ $$$$$$$$/ $$$$$$$$/ $$  \  /$$/ $$ |  $$ |$$ | /$$/ $$$$$$/ 
$$ |        $$ |     $$ |   $$ |__     $$  \/$$/  $$ |  $$ |$$ |/$$/    $$ |  
$$ |        $$ |     $$ |   $$    |     $$  $$/   $$ |  $$ |$$  $$<     $$ |  
$$ |        $$ |     $$ |   $$$$$/       $$$$/    $$ |  $$ |$$$$$  \    $$ |  
$$ |_____  _$$ |_    $$ |   $$ |_____     $$ |    $$ \__$$ |$$ |$$  \  _$$ |_ 
$$       |/ $$   |   $$ |   $$       |    $$ |    $$    $$/ $$ | $$  |/ $$   |
$$$$$$$$/ $$$$$$/    $$/    $$$$$$$$/     $$/      $$$$$$/  $$/   $$/ $$$$$$/ 
""" + "\033[0m")
    nonebot.logger.info(
        f"Run Liteyuki with Python{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} "
        f"at {sys.executable}"
    )

    nonebot.logger.info(f"{__NAME__} {__VERSION__}({__VERSION_I__}) is running")
