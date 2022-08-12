#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import shutil
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
from src.extraApi.base import ExConfig
from src.extraApi.base import ExtraData

if not os.path.exists(os.path.join(ExConfig.root_path, ".env")):
    port = input("请输入go-cqhttp端口号:")
    superuser = input("请输入超级用户qq号(多个请逗号分隔):")
    bot_name = input("请输入机器人昵称:")
    with open(os.path.join(ExConfig.root_path, ".env"), "w", encoding="utf-8") as file:
        file.write('''ENVIRONMENT=prod
HOST=127.0.0.1
PORT=%s
SUPERUSERS=[%s]
SESSION_EXPIRE_TIMEOUT=300
DEBUG=false
FASTAPI_RELOAD=false
NICKNAME=["%s"]
SESSION_RUNNING_EXPRESSION="轻雪脑抽中..."
COMMAND_START=[""]
APSCHEDULER_CONFIG={"apscheduler.timezone": "Asia/Shanghai"}
APSCHEDULER_AUTOSTART=true''' % (port, superuser, bot_name))

if os.path.exists("update_init.py"):
    os.system('"%s" update_init.py' % sys.executable)
    if asyncio.run(ExtraData.get_global_data(key="remove_init_file", default=True)):
        os.remove("update_init.py")
try:
    os.mkdir(os.path.join(ExConfig.root_path, "resource", "customize"))
except:
    pass
for templatefile in os.listdir(os.path.join(ExConfig.root_path, "resource", "customize_templates")):
    if not os.path.exists(os.path.join(ExConfig.root_path, "resources", "customize", f"{templatefile}")):
        shutil.copyfile(os.path.join(ExConfig.root_path, "resource", "customize_templates", f"{templatefile}"), os.path.join(ExConfig.root_path, "resource", "customize", f"{templatefile}"))

nonebot.init(
    _env_file=".env",
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
