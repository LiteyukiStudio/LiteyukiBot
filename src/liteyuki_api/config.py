import os.path
import json

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
    nonebot.logger.info("轻雪初始化完成")

