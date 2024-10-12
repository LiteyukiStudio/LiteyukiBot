"""
语言模块,添加对多语言的支持
"""

import json
import locale
import os
from typing import Any, overload

import nonebot

from .config import config, get_config
from .data_manager import User, user_db

_language_data = {
    "en": {
        "name": "English",
    }
}

_user_lang = {"user_id": "zh-CN"}


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
        nonebot.logger.debug(f"Loaded language data from {file_path}")
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
        nonebot.logger.debug(f"Loaded language data from {file_path}")
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
    # 三重fallback
    # 用户语言 > 默认语言/系统语言 > zh-CN
    def __init__(self, lang_code: str = None, fallback_lang_code: str = None):
        self.lang_code = lang_code

        if self.lang_code is None:
            self.lang_code = get_default_lang_code()

        self.fallback_lang_code = fallback_lang_code
        if self.fallback_lang_code is None:
            self.fallback_lang_code = config.get(
                "default_language", get_system_lang_code()
            )

    def _get(self, item: str, *args, **kwargs) -> str | Any:
        """
        获取当前语言文本，kwargs中的default参数为默认文本

        **请不要重写本函数**

        Args:
            item:   文本键
            *args:  格式化参数
            **kwargs: 格式化参数

        Returns:
            str: 当前语言的文本

        """
        default = kwargs.pop("default", None)
        fallback = (self.lang_code, self.fallback_lang_code, "zh-CN")

        for lang_code in fallback:
            if lang_code in _language_data and item in _language_data[lang_code]:
                trans: str = _language_data[lang_code][item]
                try:
                    return trans.format(*args, **kwargs)
                except Exception as e:
                    nonebot.logger.warning(f"Failed to format language data: {e}")
                    return trans
        return default or item

    def get(self, item: str, *args, **kwargs) -> str | Any:
        """
        获取当前语言文本，kwargs中的default参数为默认文本
        Args:
            item:   文本键
            *args:  格式化参数
            **kwargs: 格式化参数

        Returns:
            str: 当前语言的文本

        """
        return self._get(item, *args, **kwargs)

    def get_many(self, *args: str, **kwargs) -> dict[str, str]:
        """
        获取多个文本
        Args:
            *args:  文本键
            **kwargs: 文本键和默认文本

        Returns:
            dict: 多个文本
        """
        args_data = {item: self.get(item) for item in args}
        kwargs_data = {
            item: self.get(item, default=default) for item, default in kwargs.items()
        }
        args_data.update(kwargs_data)
        return args_data


def change_user_lang(user_id: str, lang_code: str):
    """
    修改用户的语言，同时储存到数据库和内存中
    """
    user = user_db.where_one(
        User(), "user_id = ?", user_id, default=User(user_id=user_id)
    )
    user.profile["lang"] = lang_code
    user_db.save(user)
    _user_lang[user_id] = lang_code


def get_user_lang(user_id: str) -> Language:
    """
    获取用户的语言实例，优先从内存中获取
    """
    user_id = str(user_id)

    if user_id not in _user_lang:
        nonebot.logger.debug(f"Loading user language for {user_id}")
        user = user_db.where_one(
            User(),
            "user_id = ?",
            user_id,
            default=User(user_id=user_id, username="Unknown"),
        )
        lang_code = user.profile.get("lang", get_default_lang_code())
        _user_lang[user_id] = lang_code

    return Language(_user_lang[user_id])


def get_system_lang_code() -> str:
    """
    获取系统语言代码
    """
    return locale.getdefaultlocale()[0].replace("_", "-")


def get_default_lang_code() -> str:
    """
    获取默认语言代码，若没有设置则使用系统语言
    Returns:

    """
    return get_config("default_language", default=get_system_lang_code())


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
