# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/29 下午12:02
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : translator.py
@Software: PyCharm
"""
from typing import Optional

from translate import Translator  # type: ignore

# 特殊映射语言
i18n_lang2googletrans_lang = {
        "zh-Hans": "zh-cn",
        "zh-Hant": "zh-tw",
        "en"     : "en",
}


def get_google_lang(lang: str) -> str:
    """
    Get google translate language
    Args:
        lang: language
    Returns:
        google translate language
    """
    return i18n_lang2googletrans_lang.get(lang, lang)


def translate(text: str, lang: str, source_lang: str) -> str:
    """
    Translate text to target language
    Args:
        source_lang:
        text: text
        lang: target language
    Returns:
        translated text
    """
    if lang == source_lang:
        return text
    google_lang = get_google_lang(lang)
    return Translator(to_lang=google_lang, from_lang=source_lang).translate(text)
