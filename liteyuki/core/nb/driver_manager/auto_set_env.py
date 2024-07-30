import os

import dotenv
import nonebot

from .defines import *


def auto_set_env(config: dict):
    dotenv.load_dotenv(".env")
    if os.getenv("DRIVER", None) is not None:
        nonebot.logger.info("Driver already set in environment variable, skip auto configure.")
        return
    if config.get("satori", {'enable': False}).get("enable", False):
        os.environ["DRIVER"] = get_driver_string(ASGI_DRIVER, HTTPX_DRIVER, WEBSOCKETS_DRIVER)
        nonebot.logger.info("Enable Satori, set driver to ASGI+HTTPX+WEBSOCKETS")
    else:
        os.environ["DRIVER"] = get_driver_string(ASGI_DRIVER)
        nonebot.logger.info("Disable Satori, set driver to ASGI")
    return
