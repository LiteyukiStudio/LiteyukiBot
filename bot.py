#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time

from src.liteyuki_api.data import Data
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter
nonebot.init()
app = nonebot.get_asgi()

driver = nonebot.get_driver()
driver.register_adapter(ONEBOT_V11Adapter)
nonebot.load_from_toml("pyproject.toml")
Data(Data.globals, 0).set_data(key="start_time", value=list(time.localtime()))
if __name__ == "__main__":
    nonebot.logger.warning("Always use `nb run` to start the bot instead of manually running!")
    nonebot.run(app="__mp_main__:app")
