import os

import nonebot
import yaml
from pydantic import BaseModel

from liteyuki.utils.tools import random_hex_string

config = {}  # 全局配置，确保加载后读取


class BasicConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 20216
    superusers: list[str] = []
    command_start: list[str] = ["/", ""]
    nickname: list[str] = [f"LiteyukiBot-{random_hex_string(6)}"]


def load_from_yaml(file: str) -> dict:
    global config
    nonebot.logger.debug("Loading config from %s" % file)
    if not os.path.exists(file):
        nonebot.logger.warning(f"Config file {file} not found, created default config, please modify it and restart")
        with open(file, "w", encoding="utf-8") as f:
            yaml.dump(BasicConfig().dict(), f, default_flow_style=False)

    with open(file, "r", encoding="utf-8") as f:
        conf = init_conf(yaml.load(f, Loader=yaml.FullLoader))
        config = conf
        if conf is None:
            nonebot.logger.warning(f"Config file {file} is empty, use default config. please modify it and restart")
            conf = BasicConfig().dict()
        return conf


def init_conf(conf: dict) -> dict:
    if "" not in conf.get("command_start", []):
        conf["alconna_use_command_start"] = True
    return conf
