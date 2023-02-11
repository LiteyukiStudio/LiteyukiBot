#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter

from src.liteyuki_api.config import init
# 初始化轻雪
init()

# 初始化Nonebot
nonebot.init(apscheduler_config={
    "apscheduler.timezone": "Asia/Shanghai"
})
app = nonebot.get_asgi()
driver = nonebot.get_driver() 

driver.register_adapter(ONEBOT_V11Adapter)


nonebot.load_plugin("nonebot_plugin_apscheduler")
nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run(app="__mp_main__:app")
