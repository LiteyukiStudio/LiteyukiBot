#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter
# Custom your logger
# 
# from nonebot.log import logger, default_format
# logger.add("error.log",
#            rotation="00:00",
#            diagnose=False,
#            level="ERROR",
#            format=default_format)

# You can pass some keyword args config to init function
# 外部api路径加入运行目录
sys.path.append(os.path.realpath(os.path.dirname(__file__)) + "/src/liteyuki")
nonebot.init(
    _env_file=".env.dev",
    apscheduler_autostart=True
)
app = nonebot.get_asgi()

driver = nonebot.get_driver()
driver.register_adapter(ONEBOT_V11Adapter)


# Please DO NOT modify this file unless you know what you are doing!
# As an alternative, you should use command `nb` or modify `pyproject.toml` to load plugins
nonebot.load_from_toml("pyproject.toml")

# Modify some config / config depends on loaded configs
# 
# config = driver.config
# do something...


if __name__ == "__main__":
    nonebot.logger.warning("Always use `nb run` to start the bot instead of manually running!")
    nonebot.run(app="__mp_main__:app")
