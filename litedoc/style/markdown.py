# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/28 下午3:39
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : markdown.py
@Software: PyCharm
"""
from typing import Optional

from litedoc.syntax.astparser import AstParser
from litedoc.syntax.node import *
from litedoc.i18n import get_text


def generate(parser: AstParser, lang: str, frontmatter: Optional[dict] = None, style: str = "google") -> str:
    """
    Generate markdown style document from ast
    You can modify this function to generate markdown style that enjoys you
    Args:
        parser:
        lang: language
        frontmatter:
        style: style of docs
    Returns:
        markdown style document
    """
    if frontmatter is not None:
        md = "---\n"
        for k, v in frontmatter.items():
            md += f"{k}: {v}\n"
        md += "---\n"
    else:
        md = ""

    # var > func > class

    """遍历函数"""
    for func in parser.functions:
        if func.name.startswith("_"):
            continue
        md += func.markdown(lang)

    """遍历类"""

    for cls in parser.classes:
        md += cls.markdown(lang)

    """遍历变量"""
    for var in parser.variables:
        md += f"### ***var*** `{var.name} = {var.value}`\n\n"
        if var.type != TypeHint.NO_TYPEHINT:
            md += f"- **{get_text(lang, 'type')}**: `{var.type}`\n\n"

        if var.docs is not None:
            md += f"- **{get_text(lang, 'desc')}**: {var.docs}\n\n"

    return md
