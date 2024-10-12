import os
import platform
from typing import List

import nonebot
import yaml
from pydantic import BaseModel

from ..message.tools import random_hex_string


config = {}  # 全局配置，确保加载后读取


class SatoriNodeConfig(BaseModel):
    host: str = ""
    port: str = "5500"
    path: str = ""
    token: str = ""


class SatoriConfig(BaseModel):
    comment: str = (
        "These features are still in development. Do not enable in production environment."
    )
    enable: bool = False
    hosts: List[SatoriNodeConfig] = [SatoriNodeConfig()]


class BasicConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 20216
    superusers: list[str] = []
    command_start: list[str] = ["/", ""]
    nickname: list[str] = [f"LiteyukiBot-{random_hex_string(6)}"]
    satori: SatoriConfig = SatoriConfig()
    data_path: str = "data/liteyuki"
    chromium_path: str = (
        "/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome"  # type: ignore
        if platform.system() == "Darwin"
        else (
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
            if platform.system() == "Windows"
            else "/usr/bin/chromium-browser"
        )
    )


def load_from_yaml(file_: str) -> dict:
    global config
    nonebot.logger.debug("Loading config from %s" % file_)
    if not os.path.exists(file_):
        nonebot.logger.warning(
            f"Config file {file_} not found, created default config, please modify it and restart"
        )
        with open(file_, "w", encoding="utf-8") as f:
            yaml.dump(BasicConfig().dict(), f, default_flow_style=False)

    with open(file_, "r", encoding="utf-8") as f:
        conf = init_conf(yaml.load(f, Loader=yaml.FullLoader))
        config = conf
        if conf is None:
            nonebot.logger.warning(
                f"Config file {file_} is empty, use default config. please modify it and restart"
            )
            conf = BasicConfig().dict()
        return conf


def get_config(key: str, default=None):
    """获取配置项，优先级：bot > config > db > yaml"""
    try:
        bot = nonebot.get_bot()
    except:
        bot = None

    if bot is None:
        bot_config = {}
    else:
        bot_config = bot.config.dict()

    if key in bot_config:
        return bot_config[key]

    elif key in config:
        return config[key]

    elif key in load_from_yaml("config.yml"):
        return load_from_yaml("config.yml")[key]

    else:
        return default


def init_conf(conf: dict) -> dict:
    """
    初始化配置文件，确保配置文件中的必要字段存在，且不会冲突
    Args:
        conf:

    Returns:

    """
    # 若command_start中无""，则添加必要命令头，开启alconna_use_command_start防止冲突
    # 以下内容由于issue #53 被注释
    # if "" not in conf.get("command_start", []):
    #     conf["alconna_use_command_start"] = True
    return conf
    pass
