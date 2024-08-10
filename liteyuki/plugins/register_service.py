# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/10 下午11:25
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : register_service.py
@Software: PyCharm
"""
import json
import os.path
import platform

import requests
from git import Repo
from liteyuki.plugin import PluginMetadata
from liteyuki import get_bot, logger

__plugin_meta__ = PluginMetadata(
    name="注册服务",
)

liteyuki = get_bot()
commit_hash = Repo(".").head.commit.hexsha


def register_bot():
    url = "https://api.liteyuki.icu/register"
    data = {
            "name"     : "LiteyukiBot",
            "version"  : "RollingUpdate",
            "hash"     : commit_hash,
            "version_i": 0,
            "python"   : f"{platform.python_implementation()} {platform.python_version()}",
            "os"       : f"{platform.system()} {platform.version()} {platform.machine()}"
    }
    try:
        logger.info("Waiting for register to Liteyuki...")
        resp = requests.post(url, json=data, timeout=(10, 15))
        if resp.status_code == 200:
            data = resp.json()
            if liteyuki_id := data.get("liteyuki_id"):
                with open("data/liteyuki/liteyuki.json", "wb") as f:
                    f.write(json.dumps(data).encode("utf-8"))
                logger.success(f"Register {liteyuki_id} to Liteyuki successfully")
            else:
                raise ValueError(f"Register to Liteyuki failed: {data}")

    except Exception as e:
        logger.warning(f"Register to Liteyuki failed, but it's no matter: {e}")


@liteyuki.on_before_start
async def _():
    if not os.path.exists("data/liteyuki/liteyuki.json"):
        register_bot()
