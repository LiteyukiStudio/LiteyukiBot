import os

import nonebot
import yaml
from pydantic import BaseModel

from .data_manager import StoredConfig, common_db
from .ly_typing import T_Bot
from ..message.tools import random_hex_string

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


def get_config(key: str, bot: T_Bot = None, default=None):
    """获取配置项，优先级：bot > config > db > yaml"""
    if bot is None:
        bot_config = {}
    else:
        bot_config = bot.config.dict()
    if key in bot_config:
        return bot_config[key]

    elif key in config:
        return config[key]

    elif key in common_db.first(StoredConfig(), default=StoredConfig()).config:
        return common_db.first(StoredConfig(), default=StoredConfig()).config[key]

    elif key in load_from_yaml("config.yml"):
        return load_from_yaml("config.yml")[key]

    else:
        return default


def init_conf(conf: dict) -> dict:
    if "" not in conf.get("command_start", []):
        conf["alconna_use_command_start"] = True
    return conf
