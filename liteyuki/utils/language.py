"""
语言模块,添加对多语言的支持
"""

import json
import locale
import os
from typing import Any

import nonebot

from .config import config
from .data_manager import User, user_db

_default_lang_code = "en"
_language_data = {
        "en": {
                "name": "English",
        }
}


def load_from_lang(file_path: str, lang_code: str = None):
    """
    从lang文件中加载语言数据，用于简单的文本键值对

    Args:
        file_path: lang文件路径
        lang_code: 语言代码，如果为None则从文件名中获取
    """
    try:
        if lang_code is None:
            lang_code = os.path.basename(file_path).split(".")[0]
        with open(file_path, "r", encoding="utf-8") as file:
            data = {}
            for line in file:
                line = line.strip()
                if not line or line.startswith("#"):  # 空行或注释
                    continue
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip()
            if lang_code not in _language_data:
                _language_data[lang_code] = {}
            _language_data[lang_code].update(data)
    except Exception as e:
        nonebot.logger.error(f"Failed to load language data from {file_path}: {e}")


def load_from_json(file_path: str, lang_code: str = None):
    """
    从json文件中加载语言数据，可以定义一些变量

    Args:
        lang_code: 语言代码，如果为None则从文件名中获取
        file_path: json文件路径
    """
    try:
        if lang_code is None:
            lang_code = os.path.basename(file_path).split(".")[0]
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
            if lang_code not in _language_data:
                _language_data[lang_code] = {}
            _language_data[lang_code].update(data)
    except Exception as e:
        nonebot.logger.error(f"Failed to load language data from {file_path}: {e}")


def load_from_dir(dir_path: str):
    """
    从目录中加载语言数据

    Args:
        dir_path: 目录路径
    """
    for file in os.listdir(dir_path):
        try:
            file_path = os.path.join(dir_path, file)
            if os.path.isfile(file_path):
                if file.endswith(".lang"):
                    load_from_lang(file_path)
                elif file.endswith(".json"):
                    load_from_json(file_path)
        except Exception as e:
            nonebot.logger.error(f"Failed to load language data from {file}: {e}")
            continue


def load_from_dict(data: dict, lang_code: str):
    """
    从字典中加载语言数据

    Args:
        lang_code: 语言代码
        data: 字典数据
    """
    if lang_code not in _language_data:
        _language_data[lang_code] = {}
    _language_data[lang_code].update(data)


class Language:
    def __init__(self, lang_code: str = None, fallback_lang_code: str = "en"):
        if lang_code is None:
            lang_code = get_system_lang_code()
        self.lang_code = lang_code
        self.fallback_lang_code = fallback_lang_code

    def get(self, item: str, *args, **kwargs) -> str | Any:
        """
        获取当前语言文本
        Args:
            item:   文本键
            *args:  格式化参数
            **kwargs: 格式化参数

        Returns:
            str: 当前语言的文本

        """
        default = kwargs.pop("default", None)

        try:
            if self.lang_code in _language_data and item in _language_data[self.lang_code]:
                return _language_data[self.lang_code][item].format(*args, **kwargs)
            if self.fallback_lang_code in _language_data and item in _language_data[self.fallback_lang_code]:
                return _language_data[self.fallback_lang_code][item].format(*args, **kwargs)
            return default or item
        except Exception as e:
            nonebot.logger.error(f"Failed to get language text or format: {e}")
            return default or item

    def get_many(self, *args) -> dict[str, str]:
        """
        获取多个文本
        Args:
            *args: 文本键

        Returns:
            dict: 文本字典
        """
        d = {}
        for item in args:
            d[item] = self.get(item)
        return d


def get_user_lang(user_id: str) -> Language:
    """
    获取用户的语言代码
    """
    user = user_db.first(User(), "user_id = ?", user_id, default=User(
        user_id=user_id,
        username="Unknown"
    ))

    return Language(user.profile.get("lang", config.get("default_language", get_system_lang_code())))


def get_system_lang_code() -> str:
    """
    获取系统语言代码
    """
    return locale.getdefaultlocale()[0].replace('_', '-')


def get_default_lang() -> Language:
    """
    获取配置默认/系统语言
    """
    return Language(config.get("default_language", get_system_lang_code()))


def get_all_lang() -> dict[str, str]:
    """
    获取所有语言
    Returns
        {'en': 'English'}
    """
    d = {}
    for key in _language_data:
        d[key] = _language_data[key].get("language.name", key)
    return d
