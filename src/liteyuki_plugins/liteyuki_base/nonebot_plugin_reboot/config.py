from typing import List, Optional

from nonebot import get_driver
from pydantic import BaseSettings


class Config(BaseSettings):
    reboot_load_command: bool = True
    reboot_grace_time_limit: int = 20

    class Config:
        extra = "ignore"


global_config = get_driver().config
plugin_config = Config(**global_config.dict())
