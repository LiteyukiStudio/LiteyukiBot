import os

from nonebot import logger

from src.liteyuki_api.config import Path


def update_resource():
    """
    有就更新，没有就克隆
    """
    os.system("")
    if os.path.exists(os.path.join(Path.res, ".git")) and os.path.exists(os.path.join(Path.res, "version.json")):
        logger.info("Updating Liteyuki Resource")
        os.system(f"cd src/resource ; pwd ; "
                  f"git fetch --all & "
                  f"git reset --hard origin/master & "
                  f"git pull https://gitee.com/snowykami/liteyuki-resource ")
    else:
        logger.info("Not Found Liteyuki, Resource, Cloning...")
        os.system(f"git clone https://gitee.com/snowykami/liteyuki-resource src/resource")


def update_liteyuki():
    logger.info("Updating Liteyuki Bot")
    os.system("git fetch --all & git reset --hard origin/master & git pull origin master")
