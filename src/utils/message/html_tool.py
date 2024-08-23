import os
# import time

# from typing import Literal

import aiofiles
import nonebot
from src.utils.htmlrender import (
    template_to_html,
    template_to_pic,
    # get_new_page,
)
from .tools import random_hex_string


async def template2html(
    template: str,
    templates: dict,
) -> str:
    """
    Args:
        template: str: 模板文件
        **templates: dict: 模板参数
    Returns:
        HTML 正文
    """
    template_path = os.path.dirname(template)
    template_name = os.path.basename(template)
    return await template_to_html(template_path, template_name, **templates)


async def template2image(
    template: str,
    templates: dict,
    wait: int = 1,
    scale_factor: float = 1,
    debug: bool = False,
) -> bytes:
    """
    template -> html -> image
    Args:
        debug: 输入渲染好的 html
        wait: 等待时间，单位秒
        pages: 页面参数
        template: str: 模板文件
        templates: dict: 模板参数
        scale_factor: 缩放因子，越高越清晰
    Returns:
        图片二进制数据
    """
    template_path = os.path.dirname(template)
    template_name = os.path.basename(template)

    if debug:
        # 重载资源
        raw_html = await template_to_html(
            template_name=template_name,
            template_path=template_path,
            **templates,
        )
        random_file_name = f"debug-{random_hex_string(6)}.html"
        async with aiofiles.open(
            os.path.join(template_path, random_file_name), "w", encoding="utf-8"
        ) as f:
            await f.write(raw_html)
        nonebot.logger.info("Debug HTML: %s" % f"{random_file_name}")

    return await template_to_pic(
        template_name=template_name,
        template_path=template_path,
        templates=templates,
        wait=wait,
        viewport={
            "width": 1080,
            "height": 10,
            "deviceScaleFactor": scale_factor,
        },
    )
