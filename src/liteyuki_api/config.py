import asyncio
import os.path
import json
import sys

import nonebot


class Path:
    root = os.path.abspath(os.path.join(__file__, "../../.."))
    src = os.path.join(root, "src")
    config = os.path.join(src, "config")
    data = os.path.join(src, "data")
    res = os.path.join(src, "resource")
    cache = os.path.join(src, "cache")


config_data = json.load(open(os.path.join(Path.config, "config.json"), encoding="utf-8"))



def init():
    for f in config_data.get("necessary_path", []):
        if not os.path.exists(os.path.join(Path.root, f)):
            os.makedirs(os.path.join(Path.root, f))
    if not os.path.exists(os.path.join(Path.root, ".env")):
        f = open(os.path.join(Path.root, ".env"), "w", encoding="utf-8")
        for k, v in config_data.get("init_env", {}).items():
            f.write("%s=%s\n" % (k, v))
        f.close()
        nonebot.logger.info(".env文件已生成，请自行修改配置后重启本程序")
        input("按回车或关掉窗口退出本程序...")
        sys.exit(0)

    nonebot.logger.info("轻雪初始化完成")
