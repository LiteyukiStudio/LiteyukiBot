import json
import os
import random
from typing import Iterable

import nonebot

word_bank: dict[str, set[str]] = {}


def load_from_file(file_path: str):
    """
    从json文件中加载词库

    Args:
        file_path: 文件路径
    """
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)
        for key, value_list in data.items():
            if key not in word_bank:
                word_bank[key] = set()
            word_bank[key].update(value_list)

    nonebot.logger.debug(f"Loaded word bank from {file_path}")


def load_from_dir(dir_path: str):
    """
    从目录中加载词库

    Args:
        dir_path: 目录路径
    """
    for file in os.listdir(dir_path):
        try:
            file_path = os.path.join(dir_path, file)
            if os.path.isfile(file_path):
                if file.endswith(".json"):
                    load_from_file(file_path)
        except Exception as e:
            nonebot.logger.error(f"Failed to load language data from {file}: {e}")
            continue


def get_reply(kws: Iterable[str]) -> str | None:
    """
    获取回复
    Args:
        kws: 关键词
    Returns:
    """
    for kw in kws:
        if kw in word_bank:
            return random.choice(list(word_bank[kw]))

    return None
