# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/22 下午2:17
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : liteyuki_docs.py
@Software: PyCharm
"""
from liteyuki import get_bot, logger
from liteyuki.utils import IS_MAIN_PROCESS
from liteyuki.plugin import PluginMetadata, PluginType

from fastapi import FastAPI
import uvicorn

__plugin_meta__ = PluginMetadata(
    name="轻雪文档 Liteyuki Docs",
    type=PluginType.SERVICE,
)

docs_root_path = "docs/.vuepress/dist"

app = FastAPI()


@app.get("/docs")
async def read_root():
    return {
            "Hello": "World"
            }


def start_server():
    logger.success("Docs server started.")
    uvicorn.run(app, host="127.0.0.1", port=8000, )


if IS_MAIN_PROCESS:
    bot = get_bot()
    bot.process_manager.add_target("liteyuki_docs_server", start_server)
