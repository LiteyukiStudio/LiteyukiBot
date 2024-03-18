"""
语言模块,添加对多语言的支持
"""

import json
import os
from typing import Any

import nonebot

from src.utils.data_manager import UserModel, user_db

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
            lang_code = os.path.basename(file_path).split('.')[0]
        with open(file_path, 'r', encoding='utf-8') as file:
            data = {}
            for line in file:
                line = line.strip()
                if not line or line.startswith('#'):  # 空行或注释
                    continue
                key, value = line.split('=', 1)
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
            lang_code = os.path.basename(file_path).split('.')[0]
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            if lang_code not in _language_data:
                _language_data[lang_code] = {}
            _language_data[lang_code].update(data)
    except Exception as e:
        nonebot.logger.error(f"Failed to load language data from {file_path}: {e}")


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
    def __init__(self, lang_code: str = "en", fallback_lang_code: str = "en"):
        self.lang_code = lang_code
        self.fallback_lang_code = fallback_lang_code

    def get(self, item: str, *args) -> str | Any:
        """
        获取当前语言文本
        Args:
            item:   文本键
            *args:  格式化参数

        Returns:
            str: 当前语言的文本

        """
        try:
            if self.lang_code in _language_data and item in _language_data[self.lang_code]:
                return _language_data[self.lang_code][item].format(*args)
            if self.fallback_lang_code in _language_data and item in _language_data[self.fallback_lang_code]:
                return _language_data[self.fallback_lang_code][item].format(*args)
            return item
        except Exception as e:
            nonebot.logger.error(f"Failed to get language text or format: {e}")
            return item


def get_user_lang(user_id: str) -> Language:
    """
    获取用户的语言代码
    """
    user = user_db.first(UserModel, "id = ?", user_id, default=UserModel(id=user_id, username="Unknown", lang="en"))
    return Language(user.lang)
